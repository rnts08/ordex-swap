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
    
    # Set DB_PATH environment variable for migration script
    os.environ["DB_PATH"] = db_path
    
    # Ensure swap-service is in path
    swap_service_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "swap-service"
    )
    if swap_service_path not in sys.path:
        sys.path.insert(0, swap_service_path)
    
    # Ensure app directory is in path
    app_path = os.path.dirname(os.path.dirname(__file__))
    if app_path not in sys.path:
        sys.path.insert(0, app_path)
    
    # Run migrations using standalone scripts
    from migrations.migrate_schema import run_migrations
    from migrations.migrate_settings import migrate_settings
    
    # Create database if it doesn't exist
    if not os.path.exists(db_path):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        open(db_path, "a").close()
    
    # Run schema migrations first
    run_migrations()
    
    # Then run settings migrations
    migrate_settings()
    
    return db_path
