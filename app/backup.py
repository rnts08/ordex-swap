#!/usr/bin/env python3
"""
Backup script for OrdexSwap.

Backups:
- Database (SQLite)
- Wallet data directories (OXC and OXG)

Usage:
    # Run manually:
    python backup.py

    # Run with custom paths:
    DB_PATH=/app/data/ordex.db \
    ORDEXCOIND_DATADIR=/app/data/oxc \
    ORDEXGOLDD_DATADIR=/app/data/oxg \
    DATA_DIR=/app/data \
    python backup.py
"""

import os
import sys
import sqlite3
import tarfile
import shutil
import logging
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


def backup_database(db_path: str, temp_dir: str) -> str:
    """Dump SQLite database to a SQL file."""
    if not os.path.exists(db_path):
        logger.warning(f"Database not found at {db_path}, skipping database backup")
        return None

    db_dump_path = os.path.join(temp_dir, "ordex.db.sql")
    try:
        conn = sqlite3.connect(db_path)
        with open(db_dump_path, "w") as f:
            for line in conn.iterdump():
                f.write(f"{line}\n")
        conn.close()
        logger.info(f"Database backed up to {db_dump_path}")
        return db_dump_path
    except Exception as e:
        logger.error(f"Failed to backup database: {e}")
        return None


def backup_wallet_dat(datadir: str, coin_name: str, temp_dir: str) -> str:
    """Backup wallet data directory."""
    if not os.path.exists(datadir):
        logger.warning(
            f"Wallet data not found at {datadir}, skipping {coin_name} wallet backup"
        )
        return None

    wallet_dat = os.path.join(datadir, "wallets", "wallet.dat")
    if not os.path.exists(wallet_dat):
        wallet_dat = os.path.join(datadir, "wallet.dat")

    if not os.path.exists(wallet_dat):
        logger.warning(f"wallet.dat not found for {coin_name}, skipping")
        return None

    dest = os.path.join(temp_dir, f"{coin_name.lower()}_wallet.dat")
    shutil.copy2(wallet_dat, dest)
    logger.info(f"{coin_name} wallet backed up to {dest}")
    return dest


def create_backup_archive(
    temp_dir: str, backup_dir: str, prefix: str = "ordex_backup"
) -> str:
    """Create tar.gz archive of all backed up files."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"{prefix}_{timestamp}.tar.gz"
    backup_path = os.path.join(backup_dir, backup_filename)

    os.makedirs(backup_dir, exist_ok=True)

    with tarfile.open(backup_path, "w:gz") as tar:
        for root, dirs, files in os.walk(temp_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, temp_dir)
                tar.add(file_path, arcname=arcname)

    logger.info(f"Backup archive created: {backup_path}")
    return backup_path


def cleanup_old_backups(backup_dir: str, keep_count: int = 24) -> None:
    """Remove old backup files, keeping the most recent ones."""
    if not os.path.exists(backup_dir):
        return

    backups = sorted(
        [
            f
            for f in os.listdir(backup_dir)
            if f.startswith("ordex_backup_") and f.endswith(".tar.gz")
        ],
        reverse=True,
    )

    for old_backup in backups[keep_count:]:
        old_path = os.path.join(backup_dir, old_backup)
        try:
            os.remove(old_path)
            logger.info(f"Removed old backup: {old_path}")
        except Exception as e:
            logger.warning(f"Failed to remove old backup {old_path}: {e}")


def run_backup() -> str:
    """Run the backup process."""
    logger.info("Starting backup...")

    backup_dir = os.path.join(DATA_DIR, "backups")
    temp_dir = os.path.join(backup_dir, "temp")

    os.makedirs(temp_dir, exist_ok=True)

    db_backup = backup_database(DB_PATH, temp_dir)
    oxc_backup = backup_wallet_dat(ORDEXCOIND_DATADIR, "OXC", temp_dir)
    oxg_backup = backup_wallet_dat(ORDEXGOLDD_DATADIR, "OXG", temp_dir)

    files_backed_up = sum(x is not None for x in [db_backup, oxc_backup, oxg_backup])

    if files_backed_up == 0:
        logger.warning("No files were backed up!")
        shutil.rmtree(temp_dir, ignore_errors=True)
        return None

    backup_path = create_backup_archive(temp_dir, backup_dir)

    shutil.rmtree(temp_dir, ignore_errors=True)

    cleanup_old_backups(backup_dir)

    logger.info("Backup complete!")
    return backup_path


if __name__ == "__main__":
    backup_path = run_backup()
    if backup_path:
        print(f"Backup created: {backup_path}")
        sys.exit(0)
    else:
        print("Backup failed")
        sys.exit(1)
