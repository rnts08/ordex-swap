"""
SQLite connection pool for OrdexSwap.

Provides thread-local connections to avoid overhead of creating
new connections for each database operation.
"""

import sqlite3
import threading
import os
import importlib
from contextlib import contextmanager
from typing import Optional


class SQLiteConnectionPool:
    """Thread-local SQLite connection pool."""

    def __init__(self, db_path: str = None, check_same_thread: bool = False):
        if db_path is None:
            config = importlib.import_module("config")
            db_path = config.DB_PATH
        # Use absolute path to ensure consistent pool instance for the same file
        self.db_path = os.path.abspath(db_path)
        self.check_same_thread = check_same_thread
        self._local = threading.local()

    def _create_connection(self) -> sqlite3.Connection:
        """Create a new SQLite connection with concurrency-optimized pragmas."""
        conn = sqlite3.connect(
            self.db_path,
            check_same_thread=self.check_same_thread,
            timeout=30.0,
        )
        conn.row_factory = sqlite3.Row
        
        # Concurrency optimizations for Gunicorn/Background threads
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA busy_timeout=30000")
        except sqlite3.Error as e:
            # We log but continue, as the basic connection is still open.
            import logging
            logging.getLogger("db_pool").warning(f"Failed to set WAL pragmas on {self.db_path}: {e}")
            
        return conn

    @property
    def connection(self) -> sqlite3.Connection:
        """Get thread-local connection, creating if needed."""
        if not hasattr(self._local, "connection") or self._local.connection is None:
            self._local.connection = self._create_connection()
        return self._local.connection

    def close(self) -> None:
        """Close thread-local connection."""
        if hasattr(self._local, "connection") and self._local.connection:
            self._local.connection.close()
            self._local.connection = None

    @contextmanager
    def get_connection(self):
        """Context manager for getting a connection."""
        conn = self.connection
        try:
            yield conn
        except Exception:
            conn.rollback()
            raise
        else:
            conn.commit()

    def execute(self, query: str, params: tuple = None):
        """Execute query with thread-local connection."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if params:
                return cursor.execute(query, params)
            return cursor.execute(query)

    def executemany(self, query: str, params_list: list):
        """Execute many with thread-local connection."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            return cursor.executemany(query, params_list)

    def fetchone(self, query: str, params: tuple = None):
        """Fetch one result."""
        cursor = self.execute(query, params)
        return cursor.fetchone()

    def fetchall(self, query: str, params: tuple = None):
        """Fetch all results."""
        cursor = self.execute(query, params)
        return cursor.fetchall()


_pools: dict = {}
_pool_lock = threading.Lock()


def get_pool(db_path: str = None) -> SQLiteConnectionPool:
    """Get or create a connection pool for the given db_path."""
    global _pools
    if db_path is None:
        config = importlib.import_module("config")
        db_path = config.DB_PATH
    db_path = os.path.abspath(db_path)
    if db_path not in _pools:
        with _pool_lock:
            if db_path not in _pools:
                _pools[db_path] = SQLiteConnectionPool(db_path)
    return _pools[db_path]


@contextmanager
def get_connection(db_path: str = None):
    """Context manager for getting a connection from the pool."""
    pool = get_pool(db_path)
    with pool.get_connection() as conn:
        yield conn


def close_pool(db_path: str = None) -> None:
    """Close connection pool(s)."""
    global _pools
    if db_path:
        if db_path in _pools:
            _pools[db_path].close()
            del _pools[db_path]
    else:
        for pool in _pools.values():
            pool.close()
        _pools.clear()
