#!/usr/bin/env python3
"""Ordex Swap Service - Main Entry Point."""

import os
import sys
import logging
import signal
import time
from dotenv import load_dotenv

# Add swap-service to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "swap-service"))

load_dotenv()

from price_oracle import PriceOracle
from wallet_rpc import OXCWallet, OXGWallet
from swap_engine import SwapEngine
from swap_history import SwapHistoryService
from price_history import PriceHistoryService
from admin_service import AdminService
from api import init_app, run_server
from daemon_manager import DaemonManager
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


def main():
    logger.info("=" * 50)
    logger.info("Ordex Swap Service")
    logger.info("=" * 50)

    logger.info(f"Testing mode: {TESTING_MODE}")
    logger.info(f"Data directory: {DATA_DIR}")
    logger.info(f"OXC datadir: {ORDEXCOIND_DATADIR}")
    logger.info(f"OXG datadir: {ORDEXGOLDD_DATADIR}")

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

    logger.info("Initializing public price oracle...")
    oracle = PriceOracle()

    logger.info(f"Connecting to OXC wallet at {OXC_RPC_URL}...")
    oxc_wallet = OXCWallet(
        OXC_RPC_URL, OXC_RPC_USER, OXC_RPC_PASSWORD, testing_mode=TESTING_MODE
    )

    logger.info(f"Connecting to OXG wallet at {OXG_RPC_URL}...")
    oxg_wallet = OXGWallet(
        OXG_RPC_URL, OXG_RPC_USER, OXG_RPC_PASSWORD, testing_mode=TESTING_MODE
    )

    def verify_wallet(
        wallet,
        label: str,
        wallet_name: str,
        retries: int = 30,
        delay: float = 2.0,
    ) -> None:
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
                        time.sleep(delay)
                        continue
                    except Exception as create_err:
                        logger.warning(f"{label} wallet load failed: {create_err}")
                        try:
                            logger.warning(
                                f"{label} wallet missing; creating {wallet_name}"
                            )
                            wallet.rpc.create_wallet(wallet_name)
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
                time.sleep(delay)

    verify_wallet(oxc_wallet, "OXC", OXC_WALLET_NAME)
    verify_wallet(oxg_wallet, "OXG", OXG_WALLET_NAME)

    logger.info("Initializing swap history service...")
    swap_history = SwapHistoryService(data_dir=DATA_DIR)

    logger.info("Initializing price history service...")
    price_history = PriceHistoryService(oracle=oracle, data_dir=DATA_DIR)

    logger.info("Initializing admin service...")
    admin_service = AdminService(db_path=DB_PATH)

    db_fee = admin_service.get_swap_fee_percent()
    if db_fee is not None:
        SWAP_FEE_PERCENT = db_fee
        logger.info(f"Using configured fee: {SWAP_FEE_PERCENT}%")
    else:
        logger.info(f"Using default fee: {SWAP_FEE_PERCENT}%")

    db_confirmations = admin_service.get_swap_confirmations_required()
    if db_confirmations is not None:
        SWAP_CONFIRMATIONS_REQUIRED = db_confirmations
        logger.info(f"Using configured confirmations: {SWAP_CONFIRMATIONS_REQUIRED}")
    else:
        logger.info(f"Using default confirmations: {SWAP_CONFIRMATIONS_REQUIRED}")

    db_min_fee_oxc = admin_service.get_swap_min_fee("OXC")
    if db_min_fee_oxc is not None:
        SWAP_MIN_FEE_OXC = db_min_fee_oxc
        logger.info(f"Using configured min fee OXC: {SWAP_MIN_FEE_OXC}")
    else:
        logger.info(f"Using default min fee OXC: {SWAP_MIN_FEE_OXC}")

    db_min_fee_oxg = admin_service.get_swap_min_fee("OXG")
    if db_min_fee_oxg is not None:
        SWAP_MIN_FEE_OXG = db_min_fee_oxg
        logger.info(f"Using configured min fee OXG: {SWAP_MIN_FEE_OXG}")
    else:
        logger.info(f"Using default min fee OXG: {SWAP_MIN_FEE_OXG}")

    db_min_amount = admin_service.get_swap_min_amount()
    if db_min_amount is not None:
        SWAP_MIN_AMOUNT = db_min_amount
        logger.info(f"Using configured min amount: {SWAP_MIN_AMOUNT}")
    else:
        logger.info(f"Using default min amount: {SWAP_MIN_AMOUNT}")

    db_max_amount = admin_service.get_swap_max_amount()
    if db_max_amount is not None:
        SWAP_MAX_AMOUNT = db_max_amount
        logger.info(f"Using configured max amount: {SWAP_MAX_AMOUNT}")
    else:
        logger.info(f"Using default max amount: {SWAP_MAX_AMOUNT}")

    logger.info("Starting background price fetch...")
    price_history.start_background_fetch()

    logger.info("Initializing swap engine...")
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
    )
    engine.start_background_settlement()

    logger.info("Starting API server...")
    init_app(engine, oracle, price_history, swap_history, admin_service)

    backup_thread = None
    backup_stop_event = None

    if BACKUP_ENABLED:
        logger.info(
            f"Starting background backup scheduler (every {BACKUP_INTERVAL_HOURS} hour(s))..."
        )
        import threading

        backup_stop_event = threading.Event()

        def backup_loop():
            while not backup_stop_event.is_set():
                try:
                    backup_module.run_backup()
                except Exception as e:
                    logger.error(f"Backup failed: {e}")
                backup_stop_event.wait(BACKUP_INTERVAL_HOURS * 3600)

        backup_thread = threading.Thread(target=backup_loop, daemon=True)
        backup_thread.start()
    else:
        logger.info("Background backups disabled")

    logger.info("=" * 50)
    logger.info(f"Ordex Swap Service started on {API_HOST}:{API_PORT}")
    logger.info(f"Testing mode: {TESTING_MODE}")
    logger.info(f"Data directory: {DATA_DIR}")
    logger.info("=" * 50)

    def shutdown_handler(signum, frame):
        logger.info("Shutting down...")

        logger.info("Stopping price history...")
        price_history.stop_background_fetch()
        logger.info("Stopping delayed swap processing...")
        engine.stop_background_settlement()

        if backup_stop_event:
            logger.info("Stopping backup scheduler...")
            backup_stop_event.set()

        if daemon_manager:
            daemon_manager.stop_daemons()

        logger.info("Shutdown complete")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    run_server(host=API_HOST, port=API_PORT)


if __name__ == "__main__":
    main()
