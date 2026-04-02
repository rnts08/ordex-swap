#!/usr/bin/env python3
"""
Database migration orchestrator for OrdexSwap.

Applies all pending migrations from the migrations folder to the database.
Can be run safely multiple times (idempotent).

Usage:
    # Locally:
    cd app && python3 -m migrations.run_migrations

    # In Docker:
    docker exec ordex-swap-ordex-swap-1 python /app/migrations/run_migrations.py

    # With custom DB path:
    DB_PATH=/custom/path/ordex.db python3 -m migrations.run_migrations

    # Programmatically:
    from migrations.run_migrations import migrate
    migrate()
"""

import os
import sys
import sqlite3
import logging
from dotenv import load_dotenv

# Setup paths and logging
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "swap-service"))
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Import after path setup
from config import DB_PATH
from migrations.runner import run_migrations
from migrations.admin_migrations import get_admin_migrations
from migrations.swap_migrations import get_swap_migrations


def migrate() -> None:
    """Execute all pending migrations."""
    db_path = os.getenv("DB_PATH", DB_PATH)
    logger.info(f"Running migrations on database: {db_path}")

    # Ensure data directory exists
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

    # Create new database if needed
    if not os.path.exists(db_path):
        logger.info(f"Database not found at {db_path}. Creating new database...")
        # Create empty file so sqlite3 can initialize schema
        open(db_path, "a").close()

    # Connect and apply all migrations
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        logger.info("Applying admin migrations...")
        admin_migrations = get_admin_migrations()
        run_migrations(conn, admin_migrations)

        logger.info("Applying swap history migrations...")
        swap_migrations = get_swap_migrations()
        run_migrations(conn, swap_migrations)

        conn.close()
        logger.info("All migrations completed successfully.")

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise


if __name__ == "__main__":
    migrate()
