#!/usr/bin/env python3
"""Initialize base wallets for OrdexSwap."""

import os
import sys
import time
import logging
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "swap-service"))

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from wallet_rpc import OXCWallet, OXGWallet, WalletRPCError
from price_oracle import PriceOracle
from price_history import PriceHistoryService
from config import OXC_RPC_URL, OXC_RPC_USER, OXC_RPC_PASSWORD, OXC_WALLET_NAME
from config import OXG_RPC_URL, OXG_RPC_USER, OXG_RPC_PASSWORD, OXG_WALLET_NAME

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")


def ensure_wallet(
    wallet, label: str, wallet_name: str, retries: int = 10, delay: float = 2.0
) -> None:
    for attempt in range(1, retries + 1):
        try:
            info = wallet.rpc.get_wallet_info()
            logger.info("%s wallet OK: %s", label, info)
            return
        except WalletRPCError as e:
            msg = str(e)
            if "No wallet is loaded" in msg:
                logger.info(
                    "%s wallet not loaded; trying loadwallet %s", label, wallet_name
                )
                try:
                    wallet.rpc.load_wallet(wallet_name)
                    time.sleep(delay)
                    continue
                except WalletRPCError:
                    logger.info(
                        "%s wallet load failed; trying createwallet %s",
                        label,
                        wallet_name,
                    )
                    try:
                        wallet.rpc.create_wallet(wallet_name)
                        time.sleep(delay)
                        continue
                    except WalletRPCError as create_err:
                        logger.warning("%s wallet create failed: %s", label, create_err)
            if attempt == retries:
                raise
            logger.warning(
                "%s wallet not ready (attempt %s/%s): %s", label, attempt, retries, msg
            )
            time.sleep(delay)


def main() -> int:
    logger.info("Initializing base wallets...")
    oxc_wallet = OXCWallet(OXC_RPC_URL, OXC_RPC_USER, OXC_RPC_PASSWORD)
    oxg_wallet = OXGWallet(OXG_RPC_URL, OXG_RPC_USER, OXG_RPC_PASSWORD)

    ensure_wallet(oxc_wallet, "OXC", OXC_WALLET_NAME)
    ensure_wallet(oxg_wallet, "OXG", OXG_WALLET_NAME)
    logger.info("Base wallets initialized.")

    from admin_service import AdminService, validate_password

    admin_service = AdminService()
    if not admin_service.has_admin_users():
        if not ADMIN_PASSWORD:
            logger.error(
                "No admin users exist and ADMIN_PASSWORD environment variable is not set."
            )
            logger.error(
                "Please set ADMIN_USERNAME and ADMIN_PASSWORD in your .env file."
            )
            return 1

        valid, msg = validate_password(ADMIN_PASSWORD)
        if not valid:
            logger.error(f"Invalid ADMIN_PASSWORD: {msg}")
            logger.error("Password must be at least 8 characters.")
            return 1

        if admin_service.create_admin(
            ADMIN_USERNAME, ADMIN_PASSWORD, created_by="system"
        ):
            logger.info(f"Created admin user '{ADMIN_USERNAME}'")
        else:
            logger.error(f"Failed to create admin user '{ADMIN_USERNAME}'")
            return 1
    else:
        logger.info("Admin users already exist, skipping creation.")

    logger.info("Checking price history backfill...")
    oracle = PriceOracle()
    history = PriceHistoryService(oracle=oracle)
    history.ensure_backfill(hours=24)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
