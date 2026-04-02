#!/usr/bin/env python3
"""
Database schema migration script for OrdexSwap.

Applies all pending schema migrations to the database (admin, wallet actions, history).
Can be run safely multiple times (idempotent).

Usage:
    # Locally:
    cd app && python3 migrations/migrate_schema.py

    # In Docker:
    docker exec ordex-swap-ordex-swap-1 python /app/migrations/migrate_schema.py

    # With custom DB path:
    DB_PATH=/custom/path/ordex.db python3 migrations/migrate_schema.py
"""

import os
import sys
import sqlite3
import logging
from datetime import datetime, timezone
from typing import List, Tuple

# Add paths
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "swap-service"))

from dotenv import load_dotenv
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Import config after path setup
from config import DB_PATH, SWAP_EXPIRE_MINUTES


def get_all_migrations() -> List[Tuple[str, str]]:
    """Returns all admin and swap history migrations."""
    now = datetime.now(timezone.utc).isoformat()
    
    return [
        # Admin migrations
        (
            "001_initial_admin_tables",
            """
            CREATE TABLE IF NOT EXISTS admin_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT,
                created_by TEXT,
                last_login_at TEXT,
                last_ip TEXT,
                is_active INTEGER DEFAULT 1,
                updated_at TEXT
            )
            """,
        ),
        (
            "002_admin_wallets",
            """
            CREATE TABLE IF NOT EXISTS admin_wallets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                coin TEXT NOT NULL,
                purpose TEXT NOT NULL,
                address TEXT NOT NULL,
                created_at TEXT,
                updated_at TEXT,
                UNIQUE(coin, purpose)
            )
            """,
        ),
        (
            "003_app_settings",
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT
            )
            """,
        ),
        (
            "004_wallet_actions",
            """
            CREATE TABLE IF NOT EXISTS wallet_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action_type TEXT NOT NULL,
                coin TEXT NOT NULL,
                purpose TEXT,
                amount REAL,
                address TEXT,
                txid TEXT,
                performed_by TEXT NOT NULL,
                ip_address TEXT,
                created_at TEXT NOT NULL,
                details TEXT,
                status TEXT DEFAULT 'success',
                error_code TEXT
            )
            """,
        ),
        (
            "005_swaps_history",
            """
            CREATE TABLE IF NOT EXISTS swaps (
                swap_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                data_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT,
                from_coin TEXT,
                from_amount REAL
            )
            """,
        ),
        (
            "006_swap_audit_log",
            """
            CREATE TABLE IF NOT EXISTS swap_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                swap_id TEXT NOT NULL,
                old_status TEXT,
                new_status TEXT NOT NULL,
                details TEXT,
                performed_by TEXT DEFAULT 'system',
                created_at TEXT NOT NULL,
                FOREIGN KEY (swap_id) REFERENCES swaps(swap_id)
            )
            """,
        ),
        (
            "007_swaps_indexes",
            """
            CREATE INDEX IF NOT EXISTS idx_swaps_status ON swaps(status)
            """,
        ),
        (
            "008_swaps_cleanup_index",
            """
            CREATE INDEX IF NOT EXISTS idx_swaps_created_at ON swaps(created_at)
            """,
        ),
    ]


def run_migrations() -> None:
    """Execute all pending schema migrations."""
    db_path = os.getenv("DB_PATH", DB_PATH)
    logger.info(f"Running schema migrations on database: {db_path}")

    # Ensure data directory exists
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
        logger.info(f"Created database directory: {db_dir}")

    # If database doesn't exist, it will be created by sqlite3
    conn = sqlite3.connect(db_path)
    
    try:
        # Ensure schema_migrations table exists
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                migration_id TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
            """
        )
        conn.commit()

        # Get already applied migrations
        cursor = conn.execute("SELECT migration_id FROM schema_migrations")
        applied = {row[0] for row in cursor.fetchall()}

        # Get all migrations
        migrations = get_all_migrations()

        # Apply new migrations
        applied_count = 0
        skipped_count = 0

        for mid, query in migrations:
            if mid not in applied:
                logger.info(f"Applying migration: {mid}")
                try:
                    conn.execute(query)
                    conn.execute(
                        "INSERT INTO schema_migrations (migration_id, applied_at) VALUES (?, ?)",
                        (mid, datetime.now(timezone.utc).isoformat()),
                    )
                    conn.commit()
                    logger.debug(f"Migration {mid} applied successfully.")
                    applied_count += 1
                except sqlite3.Error as e:
                    conn.rollback()
                    logger.error(f"Failed to apply migration {mid}: {e}")
                    raise
            else:
                logger.debug(f"Skipping already applied migration: {mid}")
                skipped_count += 1

        logger.info(f"\nSchema migration complete: {applied_count} applied, {skipped_count} skipped.")

    finally:
        conn.close()


if __name__ == "__main__":
    run_migrations()
