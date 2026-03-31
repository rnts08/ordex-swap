import sqlite3
import logging
from datetime import datetime, timezone
from typing import List, Tuple

logger = logging.getLogger(__name__)

def run_migrations(conn: sqlite3.Connection, migrations: List[Tuple[str, str]]) -> None:
    """
    Runs a list of migrations on the given connection idempotently.
    Each migration is a tuple of (migration_id, sql_query).
    """
    # 1. Ensure schema_migrations table exists
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            migration_id TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )
    
    # 2. Get already applied migrations
    cursor = conn.execute("SELECT migration_id FROM schema_migrations")
    applied = {row[0] for row in cursor.fetchall()}
    
    # 3. Apply new migrations
    for mid, query in migrations:
        if mid not in applied:
            logger.info(f"Applying migration: {mid}")
            try:
                # Use a sub-transaction if possible, but execute() on conn is usually sufficient
                conn.execute(query)
                conn.execute(
                    "INSERT INTO schema_migrations (migration_id, applied_at) VALUES (?, ?)",
                    (mid, datetime.now(timezone.utc).isoformat())
                )
                conn.commit()
                logger.debug(f"Migration {mid} applied successfully.")
            except sqlite3.Error as e:
                conn.rollback()
                logger.error(f"Failed to apply migration {mid}: {e}")
                raise
        else:
            logger.debug(f"Migration {mid} already applied, skipping.")
