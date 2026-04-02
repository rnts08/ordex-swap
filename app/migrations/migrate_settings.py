#!/usr/bin/env python3
"""
Database settings migration script for OrdexSwap.

Adds configurable settings to the app_settings table:
- swap_confirmations_required
- swap_min_fee_OXC
- swap_min_fee_OXG
- swap_fee_percent
- swaps_enabled
- swap_min_amount
- swap_max_amount

Can be run safely multiple times (idempotent).

Usage:
    # Locally:
    cd app && python3 migrations/migrate_settings.py

    # In Docker:
    docker exec ordex-swap-ordex-swap-1 python /app/migrations/migrate_settings.py

    # With custom DB path:
    DB_PATH=/custom/path/ordex.db python3 migrations/migrate_settings.py
"""

import os
import sys
import sqlite3
from datetime import datetime, timezone

# Add paths
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "swap-service"))

from dotenv import load_dotenv
load_dotenv()

# Import config after path setup
from config import DB_PATH


def migrate_settings() -> None:
    """Add default settings to app_settings table."""
    db_path = os.getenv("DB_PATH", DB_PATH)
    print(f"Running settings migration on database: {db_path}")

    # Ensure data directory exists
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}. Skipping settings migration.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='app_settings'"
    )
    if not cursor.fetchone():
        print("app_settings table not found. Creating...")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT
            )
        """)

    settings_to_add = [
        ("swap_fee_percent", "1.0"),
        ("swap_confirmations_required", "1"),
        ("swap_min_fee_OXC", "1.0"),
        ("swap_min_fee_OXG", "1.0"),
        ("swap_min_amount", "0.0001"),
        ("swap_max_amount", "10000.0"),
        ("swap_expire_minutes", "15"),
        ("swaps_enabled", "true"),
        # Circuit breaker settings for abnormal swap ratio protection
        ("circuit_breaker_ratio", "5.0"),  # Max allowed ratio (from_amount / to_amount)
        ("circuit_breaker_enabled", "true"),
    ]

    now = datetime.now(timezone.utc).isoformat()
    updated = 0
    created = 0

    for key, default_value in settings_to_add:
        cursor.execute("SELECT value FROM app_settings WHERE key = ?", (key,))
        row = cursor.fetchone()

        if row is None:
            cursor.execute(
                "INSERT INTO app_settings (key, value, updated_at) VALUES (?, ?, ?)",
                (key, default_value, now),
            )
            created += 1
            print(f"  Created setting: {key} = {default_value}")
        else:
            print(f"  Existing setting: {key} = {row[0]} (kept)")
            updated += 1

    conn.commit()
    conn.close()

    print(f"\nSettings migration complete: {created} created, {updated} existing.")


if __name__ == "__main__":
    migrate_settings()
