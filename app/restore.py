#!/usr/bin/env python3
"""
Restore script for OrdexSwap backups.

Restores:
- Database (SQLite)
- Wallet data (OXC and OXG)

Usage:
    # List available backups:
    python restore.py --list

    # Restore from a specific backup:
    python restore.py ordex_backup_20240315_120000.tar.gz

    # Restore to custom paths:
    DB_PATH=/app/data/ordex.db \
    ORDEXCOIND_DATADIR=/app/data/oxc \
    ORDEXGOLDD_DATADIR=/app/data/oxg \
    DATA_DIR=/app/data \
    python restore.py ordex_backup_20240315_120000.tar.gz

    # In Docker:
    docker exec ordex-swap-ordex-swap-1 python /app/restore.py ordex_backup_20240315_120000.tar.gz
"""

import os
import sys
import sqlite3
import tarfile
import shutil
import logging
import argparse
from datetime import datetime
from typing import Optional, List
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "swap-service"))
load_dotenv()

from config import DB_PATH, ORDEXCOIND_DATADIR, ORDEXGOLDD_DATADIR, DATA_DIR

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def list_backups() -> list:
    """List all available backup files."""
    backup_dir = os.path.join(DATA_DIR, "backups")

    if not os.path.exists(backup_dir):
        print("No backups found.")
        return []

    backups = sorted(
        [
            f
            for f in os.listdir(backup_dir)
            if f.startswith("ordex_backup_") and f.endswith(".tar.gz")
        ],
        reverse=True,
    )

    if not backups:
        print("No backups found.")
        return []

    print("Available backups:")
    print("-" * 50)
    for backup in backups:
        backup_path = os.path.join(backup_dir, backup)
        size_mb = os.path.getsize(backup_path) / (1024 * 1024)
        mtime = datetime.fromtimestamp(os.path.getmtime(backup_path))
        print(f"  {backup} ({size_mb:.2f} MB, {mtime.strftime('%Y-%m-%d %H:%M:%S')})")

    return backups


def restore_database(db_sql_path: str, db_path: str) -> bool:
    """Restore SQLite database from SQL dump."""
    if not os.path.exists(db_sql_path):
        logger.error(f"Database backup not found: {db_sql_path}")
        return False

    try:
        if os.path.exists(db_path):
            backup_suffix = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.pre_restore"
            backup_path = f"{db_path}.{backup_suffix}"
            shutil.copy2(db_path, backup_path)
            logger.info(f"Existing database backed up to {backup_path}")

        if os.path.exists(db_path):
            os.remove(db_path)

        conn = sqlite3.connect(db_path)
        with open(db_sql_path, "r") as f:
            conn.executescript(f.read())
        conn.close()

        logger.info(f"Database restored to {db_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to restore database: {e}")
        return False


def restore_wallet(wallet_dat_path: str, datadir: str, coin_name: str) -> bool:
    """Restore wallet data directory."""
    if not os.path.exists(wallet_dat_path):
        logger.warning(f"Wallet backup not found: {wallet_dat_path}")
        return False

    try:
        os.makedirs(datadir, exist_ok=True)

        wallets_dir = os.path.join(datadir, "wallets")
        os.makedirs(wallets_dir, exist_ok=True)

        wallet_dest = os.path.join(wallets_dir, "wallet.dat")

        if os.path.exists(wallet_dest):
            backup_suffix = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.pre_restore"
            backup_path = f"{wallet_dest}.{backup_suffix}"
            shutil.copy2(wallet_dest, backup_path)
            logger.info(f"Existing {coin_name} wallet backed up to {backup_path}")

        shutil.copy2(wallet_dat_path, wallet_dest)

        logger.info(f"{coin_name} wallet restored to {wallet_dest}")
        return True
    except Exception as e:
        logger.error(f"Failed to restore {coin_name} wallet: {e}")
        return False


def restore_backup(backup_filename: str) -> bool:
    """Restore from a backup file."""
    backup_dir = os.path.join(DATA_DIR, "backups")
    backup_path = os.path.join(backup_dir, backup_filename)

    if not os.path.exists(backup_path):
        logger.error(f"Backup not found: {backup_path}")
        return False

    logger.info(f"Starting restore from {backup_filename}...")

    temp_dir = os.path.join(backup_dir, "restore_temp")

    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    os.makedirs(temp_dir)

    try:
        with tarfile.open(backup_path, "r:gz") as tar:
            tar.extractall(temp_dir)

        restored_count = 0

        db_sql = os.path.join(temp_dir, "ordex.db.sql")
        if os.path.exists(db_sql):
            if restore_database(db_sql, DB_PATH):
                restored_count += 1

        oxc_wallet = os.path.join(temp_dir, "oxc_wallet.dat")
        if os.path.exists(oxc_wallet):
            if restore_wallet(oxc_wallet, ORDEXCOIND_DATADIR, "OXC"):
                restored_count += 1

        oxg_wallet = os.path.join(temp_dir, "oxg_wallet.dat")
        if os.path.exists(oxg_wallet):
            if restore_wallet(oxg_wallet, ORDEXGOLDD_DATADIR, "OXG"):
                restored_count += 1

        shutil.rmtree(temp_dir, ignore_errors=True)

        if restored_count == 0:
            logger.error("No files were restored!")
            return False

        logger.info(f"Restore complete! {restored_count} item(s) restored.")
        return True

    except Exception as e:
        logger.error(f"Restore failed: {e}")
        shutil.rmtree(temp_dir, ignore_errors=True)
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Restore OrdexSwap from backup")
    parser.add_argument(
        "--list", "-l", action="store_true", help="List available backups"
    )
    parser.add_argument("backup", nargs="?", help="Backup filename to restore")

    args = parser.parse_args()

    if args.list:
        list_backups()
        return

    if not args.backup:
        parser.print_help()
        print("\nExamples:")
        print("  python restore.py --list              # List backups")
        print("  python restore.py ordex_backup_20240315_120000.tar.gz  # Restore")
        return

    success = restore_backup(args.backup)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
