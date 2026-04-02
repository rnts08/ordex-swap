"""Database migrations for admin, wallet actions, and settings tables."""

from datetime import datetime, timezone
from typing import List, Tuple


def get_admin_migrations() -> List[Tuple[str, str]]:
    """
    Returns all admin-related migrations.
    These are idempotent and will be skipped if already applied.
    """
    from config import SWAP_EXPIRE_MINUTES

    now = datetime.now(timezone.utc).isoformat()

    return [
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
            "004_default_settings",
            f"""
            INSERT OR IGNORE INTO app_settings (key, value, updated_at) VALUES 
            ('swaps_enabled', 'true', '{now}'),
            ('swap_fee_percent', '1.0', '{now}'),
            ('swap_confirmations_required', '1', '{now}'),
            ('swap_min_fee_OXC', '1.0', '{now}'),
            ('swap_min_fee_OXG', '1.0', '{now}'),
            ('swap_min_amount', '0.0001', '{now}'),
            ('swap_max_amount', '10000.0', '{now}'),
            ('swap_expire_minutes', '{SWAP_EXPIRE_MINUTES}', '{now}')
            """,
        ),
        (
            "005_wallet_actions",
            """
            CREATE TABLE IF NOT EXISTS wallet_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action_type TEXT NOT NULL,
                coin TEXT NOT NULL,
                purpose TEXT,
                amount REAL,
                address TEXT,
                txid TEXT,
                performed_by TEXT,
                ip_address TEXT,
                created_at TEXT,
                details TEXT,
                status TEXT DEFAULT 'pending',
                error_code TEXT
            )
            """,
        ),
        (
            "006_admin_audit_log",
            """
            CREATE TABLE IF NOT EXISTS admin_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                ip_address TEXT,
                action TEXT NOT NULL,
                result TEXT NOT NULL,
                details TEXT,
                created_at TEXT NOT NULL
            )
            """,
        ),
        (
            "007_wallet_configs",
            """
            CREATE TABLE IF NOT EXISTS wallet_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                coin TEXT UNIQUE NOT NULL,
                wallet_path TEXT NOT NULL,
                wallet_name TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            """,
        ),
        (
            "008_acknowledged_transactions",
            """
            CREATE TABLE IF NOT EXISTS acknowledged_transactions (
                txid TEXT PRIMARY KEY,
                coin TEXT NOT NULL,
                amount REAL NOT NULL,
                address TEXT,
                action TEXT NOT NULL,
                performed_by TEXT,
                details TEXT,
                created_at TEXT
            )
            """,
        ),
    ]
