import os
import logging
import signal
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "swap-service"))

from dotenv import load_dotenv

load_dotenv()

from price_oracle import PriceOracle
from wallet_rpc import OXCWallet, OXGWallet
from swap_engine import SwapEngine
from swap_history import SwapHistoryService
from price_history import PriceHistoryService
from admin_service import AdminService
from api import app, init_app
from daemon_manager import DaemonManager
from swap_cleanup import SwapCleanupJob
import backup as backup_module
from config import (
    SWAP_FEE_PERCENT,
    SWAP_MIN_FEE_OXC,
    SWAP_MIN_FEE_OXG,
    SWAP_CONFIRMATIONS_REQUIRED,
    SWAP_MIN_AMOUNT,
    SWAP_MAX_AMOUNT,
    API_HOST,
    API_PORT,
    OXC_RPC_URL,
    OXC_RPC_USER,
    OXC_RPC_PASSWORD,
    OXC_WALLET_NAME,
    OXG_RPC_URL,
    OXG_RPC_USER,
    OXG_RPC_PASSWORD,
    OXG_WALLET_NAME,
    TESTING_MODE,
    ORDEXCOIND_PATH,
    ORDEXGOLDD_PATH,
    ORDEXCOIND_DATADIR,
    ORDEXGOLDD_DATADIR,
    DATA_DIR,
    DB_PATH,
    BACKUP_ENABLED,
    BACKUP_INTERVAL_HOURS,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

daemon_manager = None
price_history = None
engine = None
cleanup_job = None
backup_thread = None
backup_stop_event = None
initialized = False


def initialize_services():
    global \
        daemon_manager, \
        price_history, \
        engine, \
        cleanup_job, \
        backup_thread, \
        backup_stop_event, \
        initialized

    if initialized:
        return

    logger.info("Initializing services...")

    os.makedirs(DATA_DIR, exist_ok=True)

    daemon_manager = DaemonManager(
        ORDEXCOIND_PATH,
        ORDEXGOLDD_PATH,
        OXC_RPC_USER,
        OXC_RPC_PASSWORD,
        OXG_RPC_USER,
        OXG_RPC_PASSWORD,
        coind_datadir=ORDEXCOIND_DATADIR,
        goldd_datadir=ORDEXGOLDD_DATADIR,
    )
    daemon_manager.start_daemons(testing_mode=TESTING_MODE)

    oracle = PriceOracle()

    oxc_wallet = OXCWallet(
        OXC_RPC_URL, OXC_RPC_USER, OXC_RPC_PASSWORD, testing_mode=TESTING_MODE
    )

    oxg_wallet = OXGWallet(
        OXG_RPC_URL, OXG_RPC_USER, OXG_RPC_PASSWORD, testing_mode=TESTING_MODE
    )

    def verify_wallet(wallet, label, wallet_name, retries=30, delay=2.0):
        attempted_create = False
        for attempt in range(1, retries + 1):
            try:
                info = wallet.rpc.get_wallet_info()
                logger.info(f"{label} wallet OK: {info}")
                return
            except Exception as e:
                if not attempted_create and "No wallet is loaded" in str(e):
                    attempted_create = True
                    try:
                        logger.warning(
                            f"{label} wallet not loaded; trying loadwallet {wallet_name}"
                        )
                        wallet.rpc.load_wallet(wallet_name)
                        import time

                        time.sleep(delay)
                        continue
                    except Exception as create_err:
                        logger.warning(f"{label} wallet load failed: {create_err}")
                        try:
                            logger.warning(
                                f"{label} wallet missing; creating {wallet_name}"
                            )
                            wallet.rpc.create_wallet(wallet_name)
                            import time

                            time.sleep(delay)
                            continue
                        except Exception as create_err:
                            logger.warning(
                                f"{label} wallet create failed: {create_err}"
                            )
                if attempt == retries:
                    logger.error(
                        f"{label} wallet check failed after {retries} attempts: {e}"
                    )
                    sys.exit(1)
                logger.warning(
                    f"{label} wallet not ready (attempt {attempt}/{retries}): {e}"
                )
                import time

                time.sleep(delay)

    verify_wallet(oxc_wallet, "OXC", OXC_WALLET_NAME)
    verify_wallet(oxg_wallet, "OXG", OXG_WALLET_NAME)

    swap_history = SwapHistoryService(data_dir=DATA_DIR)

    price_history = PriceHistoryService(oracle=oracle, data_dir=DATA_DIR)

    admin_service = AdminService(db_path=DB_PATH)

    db_fee = admin_service.get_swap_fee_percent()
    if db_fee is not None:
        global SWAP_FEE_PERCENT
        SWAP_FEE_PERCENT = db_fee

    db_confirmations = admin_service.get_swap_confirmations_required()
    if db_confirmations is not None:
        global SWAP_CONFIRMATIONS_REQUIRED
        SWAP_CONFIRMATIONS_REQUIRED = db_confirmations

    db_min_fee_oxc = admin_service.get_swap_min_fee("OXC")
    if db_min_fee_oxc is not None:
        global SWAP_MIN_FEE_OXC
        SWAP_MIN_FEE_OXC = db_min_fee_oxc

    db_min_fee_oxg = admin_service.get_swap_min_fee("OXG")
    if db_min_fee_oxg is not None:
        global SWAP_MIN_FEE_OXG
        SWAP_MIN_FEE_OXG = db_min_fee_oxg

    db_min_amount = admin_service.get_swap_min_amount()
    if db_min_amount is not None:
        global SWAP_MIN_AMOUNT
        SWAP_MIN_AMOUNT = db_min_amount

    db_max_amount = admin_service.get_swap_max_amount()
    if db_max_amount is not None:
        global SWAP_MAX_AMOUNT
        SWAP_MAX_AMOUNT = db_max_amount

    logger.info("Starting background price fetch...")
    price_history.start_background_fetch()

    engine = SwapEngine(
        price_oracle=oracle,
        oxc_wallet=oxc_wallet,
        oxg_wallet=oxg_wallet,
        history_service=swap_history,
        fee_percent=SWAP_FEE_PERCENT,
        min_amount=SWAP_MIN_AMOUNT,
        max_amount=SWAP_MAX_AMOUNT,
        confirmations_required=SWAP_CONFIRMATIONS_REQUIRED,
        min_fee_oxc=SWAP_MIN_FEE_OXC,
        min_fee_oxg=SWAP_MIN_FEE_OXG,
        admin_service=admin_service,
    )
    engine.start_background_settlement()

    cleanup_job = SwapCleanupJob(engine, db_path=DB_PATH)

    logger.info("Initializing API...")
    init_app(engine, oracle, price_history, swap_history, admin_service)

    logger.info("Starting swap cleanup job...")
    cleanup_job.start()

    if BACKUP_ENABLED:
        import threading

        backup_stop_event = threading.Event()

        def backup_loop():
            while not backup_stop_event.is_set():
                try:
                    backup_module.run_backup()
                except Exception as e:
                    logger.error(f"Backup failed: {e}")
                import time

                backup_stop_event.wait(BACKUP_INTERVAL_HOURS * 3600)

        backup_thread = threading.Thread(target=backup_loop, daemon=True)
        backup_thread.start()

    initialized = True
    logger.info("All services initialized")
    return app


def shutdown_handler(signum, frame):
    logger.info("Shutting down...")

    if price_history:
        logger.info("Stopping price history...")
        price_history.stop_background_fetch()
    if engine:
        logger.info("Stopping delayed swap processing...")
        engine.stop_background_settlement()
    if cleanup_job:
        logger.info("Stopping swap cleanup job...")
        cleanup_job.stop()
    if backup_stop_event:
        logger.info("Stopping backup scheduler...")
        backup_stop_event.set()
    if daemon_manager:
        logger.info("Stopping daemons...")
        daemon_manager.stop_daemons()

    logger.info("Shutdown complete")


signal.signal(signal.SIGINT, shutdown_handler)
signal.signal(signal.SIGTERM, shutdown_handler)

initialize_services()
