"""Test utilities for setting up migrations and database."""

import os
import sys
import sqlite3
from typing import Optional

def setup_test_db(db_path: Optional[str] = None) -> str:
    """
    Setup database for testing by running migrations.
    
    Args:
        db_path: Optional custom database path. If None, uses DB_PATH from environment.
    
    Returns:
        The path to the database that was initialized.
    """
    if db_path is None:
        db_path = os.environ.get("DB_PATH")
        if not db_path:
            raise ValueError("DB_PATH environment variable not set")
    
    # Ensure swap-service is in path
    swap_service_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "swap-service"
    )
    if swap_service_path not in sys.path:
        sys.path.insert(0, swap_service_path)
    
    # Ensure migrations are in path
    migrations_path = os.path.dirname(os.path.dirname(__file__))
    if migrations_path not in sys.path:
        sys.path.insert(0, migrations_path)
    
    # Run migrations
    from migrations.runner import run_migrations
    from migrations.admin_migrations import get_admin_migrations
    from migrations.swap_migrations import get_swap_migrations
    
    # Create database if it doesn't exist
    if not os.path.exists(db_path):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        open(db_path, "a").close()
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    # Apply migrations
    admin_migrations = get_admin_migrations()
    swap_migrations = get_swap_migrations()
    
    run_migrations(conn, admin_migrations)
    run_migrations(conn, swap_migrations)
    
    conn.close()
    
    return db_path
