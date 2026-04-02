"""Database migrations for swap history and audit tables."""

from typing import List, Tuple


def get_swap_migrations() -> List[Tuple[str, str]]:
    """
    Returns all swap-related migrations.
    These are idempotent and will be skipped if already applied.
    """
    return [
        (
            "001_initial_swaps_table",
            """
            CREATE TABLE IF NOT EXISTS swaps (
                swap_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                data_json TEXT NOT NULL,
                created_at TEXT,
                updated_at TEXT,
                completed_at TEXT,
                from_coin TEXT,
                from_amount REAL
            )
            """,
        ),
        (
            "002_swap_audit_log",
            """
            CREATE TABLE IF NOT EXISTS swap_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                swap_id TEXT NOT NULL,
                old_status TEXT,
                new_status TEXT NOT NULL,
                details TEXT,
                performed_by TEXT,
                created_at TEXT NOT NULL
            )
            """,
        ),
    ]
