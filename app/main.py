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
from api import init_app, run_server
from daemon_manager import DaemonManager
from config import (
    SWAP_FEE_PERCENT,
    SWAP_MIN_AMOUNT,
    SWAP_MAX_AMOUNT,
    API_HOST,
    API_PORT,
    NESTEX_API_KEY,
    NESTEX_API_SECRET,
    OXC_RPC_URL,
    OXC_RPC_USER,
    OXC_RPC_PASSWORD,
    OXG_RPC_URL,
    OXG_RPC_USER,
    OXG_RPC_PASSWORD,
    TESTING_MODE,
    ORDEXCOIND_PATH,
    ORDEXGOLDD_PATH,
    ORDEXCOIND_DATADIR,
    ORDEXGOLDD_DATADIR,
    DATA_DIR,
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
        coind_datadir=ORDEXCOIND_DATADIR,
        goldd_datadir=ORDEXGOLDD_DATADIR,
    )
    daemon_manager.start_daemons(testing_mode=TESTING_MODE)

    logger.info("Connecting to NestEx API...")
    oracle = PriceOracle(NESTEX_API_KEY, NESTEX_API_SECRET)

    try:
        if oracle.check_token():
            logger.info("NestEx API token validated")
        else:
            logger.warning("NestEx API token invalid - prices may be unavailable")
    except Exception as e:
        logger.warning(f"NestEx API connection failed: {e}")

    logger.info(f"Connecting to OXC wallet at {OXC_RPC_URL}...")
    oxc_wallet = OXCWallet(
        OXC_RPC_URL, OXC_RPC_USER, OXC_RPC_PASSWORD, testing_mode=TESTING_MODE
    )

    logger.info(f"Connecting to OXG wallet at {OXG_RPC_URL}...")
    oxg_wallet = OXGWallet(
        OXG_RPC_URL, OXG_RPC_USER, OXG_RPC_PASSWORD, testing_mode=TESTING_MODE
    )

    def verify_wallet(wallet, label: str, retries: int = 30, delay: float = 2.0) -> None:
        wallet_name = f"{label.lower()}_wallet"
        attempted_create = False
        for attempt in range(1, retries + 1):
            try:
                info = wallet.rpc.get_wallet_info()
                logger.info(f"{label} wallet OK: {info}")
                return
            except Exception as e:
                if (
                    not attempted_create
                    and "No wallet is loaded" in str(e)
                ):
                    attempted_create = True
                    try:
                        logger.warning(f"{label} wallet missing; creating {wallet_name}")
                        wallet.rpc.create_wallet(wallet_name)
                        time.sleep(delay)
                        continue
                    except Exception as create_err:
                        logger.warning(
                            f"{label} wallet create failed: {create_err}"
                        )
                if attempt == retries:
                    logger.error(f"{label} wallet check failed after {retries} attempts: {e}")
                    sys.exit(1)
                logger.warning(
                    f"{label} wallet not ready (attempt {attempt}/{retries}): {e}"
                )
                time.sleep(delay)

    verify_wallet(oxc_wallet, "OXC")
    verify_wallet(oxg_wallet, "OXG")

    logger.info("Initializing swap history service...")
    swap_history = SwapHistoryService(data_dir=DATA_DIR)

    logger.info("Initializing price history service...")
    price_history = PriceHistoryService(oracle=oracle, data_dir=DATA_DIR)

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
    )

    logger.info("Starting API server...")
    init_app(engine, oracle, price_history, swap_history)

    logger.info("=" * 50)
    logger.info(f"Ordex Swap Service started on {API_HOST}:{API_PORT}")
    logger.info(f"Testing mode: {TESTING_MODE}")
    logger.info(f"Data directory: {DATA_DIR}")
    logger.info("=" * 50)

    def shutdown_handler(signum, frame):
        logger.info("Shutting down...")

        logger.info("Stopping price history...")
        price_history.stop_background_fetch()

        if daemon_manager:
            daemon_manager.stop_daemons()

        logger.info("Shutdown complete")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    run_server(host=API_HOST, port=API_PORT)


if __name__ == "__main__":
    main()
