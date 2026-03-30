import logging
import sqlite3
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from werkzeug.security import generate_password_hash, check_password_hash

from config import DB_PATH

logger = logging.getLogger(__name__)


class AdminService:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or DB_PATH
        self._init_db()
        self.ensure_default_admin()

    def _init_db(self) -> None:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS admin_users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT UNIQUE NOT NULL,
                        password_hash TEXT NOT NULL,
                        created_at TEXT,
                        updated_at TEXT,
                        last_login_at TEXT
                    )
                    """
                )
                conn.execute(
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
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS app_settings (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL,
                        updated_at TEXT
                    )
                    """
                )
                conn.execute(
                    "INSERT OR IGNORE INTO app_settings (key, value, updated_at) VALUES (?, ?, ?)",
                    ("swaps_enabled", "true", datetime.now(timezone.utc).isoformat()),
                )
                conn.execute(
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
                        created_at TEXT,
                        details TEXT
                    )
                    """
                )
        except sqlite3.Error as e:
            logger.error(f"Failed to initialize admin db: {e}")

    def ensure_default_admin(self) -> None:
        try:
            with sqlite3.connect(self.db_path) as conn:
                row = conn.execute("SELECT COUNT(*) FROM admin_users").fetchone()
                count = row[0] if row else 0
                if count > 0:
                    return
                now = datetime.now(timezone.utc).isoformat()
                conn.execute(
                    """
                    INSERT INTO admin_users (username, password_hash, created_at, updated_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        "swap",
                        generate_password_hash("changeme26"),
                        now,
                        now,
                    ),
                )
                logger.warning(
                    "Created default admin user 'swap' with password 'changeme26'."
                )
        except sqlite3.Error as e:
            logger.error(f"Failed to create default admin: {e}")

    def verify_credentials(self, username: str, password: str) -> bool:
        try:
            with sqlite3.connect(self.db_path) as conn:
                row = conn.execute(
                    "SELECT id, password_hash FROM admin_users WHERE username = ?",
                    (username,),
                ).fetchone()
            if not row:
                return False
            admin_id, password_hash = row
            if not check_password_hash(password_hash, password):
                return False
            now = datetime.now(timezone.utc).isoformat()
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "UPDATE admin_users SET last_login_at = ?, updated_at = ? WHERE id = ?",
                    (now, now, admin_id),
                )
            return True
        except sqlite3.Error as e:
            logger.error(f"Failed to verify admin credentials: {e}")
            return False

    def get_or_create_wallet_address(
        self, coin: str, purpose: str, address_generator
    ) -> Optional[str]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                row = conn.execute(
                    "SELECT address FROM admin_wallets WHERE coin = ? AND purpose = ?",
                    (coin, purpose),
                ).fetchone()
                if row and row[0]:
                    return row[0]

                address = address_generator()
                now = datetime.now(timezone.utc).isoformat()
                conn.execute(
                    """
                    INSERT OR REPLACE INTO admin_wallets
                    (coin, purpose, address, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (coin, purpose, address, now, now),
                )
                return address
        except sqlite3.Error as e:
            logger.error(f"Failed to get or create admin wallet: {e}")
            return None

    def rotate_wallet_address(
        self, coin: str, purpose: str, address_generator
    ) -> Optional[str]:
        try:
            address = address_generator()
            now = datetime.now(timezone.utc).isoformat()
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO admin_wallets
                    (coin, purpose, address, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (coin, purpose, address, now, now),
                )
            return address
        except sqlite3.Error as e:
            logger.error(f"Failed to rotate admin wallet: {e}")
            return None

    def list_wallets(self) -> Dict[str, Dict[str, Any]]:
        wallets: Dict[str, Dict[str, Any]] = {}
        try:
            with sqlite3.connect(self.db_path) as conn:
                rows = conn.execute(
                    "SELECT coin, purpose, address, updated_at FROM admin_wallets"
                ).fetchall()
            for coin, purpose, address, updated_at in rows:
                wallets.setdefault(coin, {})
                wallets[coin][purpose] = {
                    "address": address,
                    "updated_at": updated_at,
                }
        except sqlite3.Error as e:
            logger.error(f"Failed to list admin wallets: {e}")
        return wallets

    def create_admin(self, username: str, password: str) -> bool:
        username = username.strip()
        if not username or not password:
            return False
        try:
            now = datetime.now(timezone.utc).isoformat()
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO admin_users (username, password_hash, created_at, updated_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (username, generate_password_hash(password), now, now),
                )
            return True
        except sqlite3.IntegrityError:
            return False
        except sqlite3.Error as e:
            logger.error(f"Failed to create admin user: {e}")
            return False

    def list_admins(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                rows = conn.execute(
                    "SELECT username, created_at, last_login_at FROM admin_users"
                ).fetchall()
            return [
                {
                    "username": row[0],
                    "created_at": row[1],
                    "last_login_at": row[2],
                }
                for row in rows
            ]
        except sqlite3.Error as e:
            logger.error(f"Failed to list admin users: {e}")
            return []

    def update_password(
        self, username: str, current_password: str, new_password: str
    ) -> bool:
        if not username or not current_password or not new_password:
            return False
        if not self.verify_credentials(username, current_password):
            return False
        try:
            now = datetime.now(timezone.utc).isoformat()
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    UPDATE admin_users
                    SET password_hash = ?, updated_at = ?
                    WHERE username = ?
                    """,
                    (generate_password_hash(new_password), now, username),
                )
            return True
        except sqlite3.Error as e:
            logger.error(f"Failed to update admin password: {e}")
            return False

    def get_swaps_enabled(self) -> bool:
        try:
            with sqlite3.connect(self.db_path) as conn:
                row = conn.execute(
                    "SELECT value FROM app_settings WHERE key = ?",
                    ("swaps_enabled",),
                ).fetchone()
            return row[0] == "true" if row else True
        except sqlite3.Error as e:
            logger.error(f"Failed to get swaps_enabled: {e}")
            return True

    def set_swaps_enabled(self, enabled: bool) -> bool:
        try:
            now = datetime.now(timezone.utc).isoformat()
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO app_settings (key, value, updated_at) VALUES (?, ?, ?)",
                    ("swaps_enabled", "true" if enabled else "false", now),
                )
            return True
        except sqlite3.Error as e:
            logger.error(f"Failed to set swaps_enabled: {e}")
            return False

    def log_wallet_action(
        self,
        action_type: str,
        coin: str,
        purpose: str = None,
        amount: float = None,
        address: str = None,
        txid: str = None,
        performed_by: str = None,
        details: str = None,
    ) -> bool:
        try:
            now = datetime.now(timezone.utc).isoformat()
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO wallet_actions 
                    (action_type, coin, purpose, amount, address, txid, performed_by, created_at, details)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        action_type,
                        coin,
                        purpose,
                        amount,
                        address,
                        txid,
                        performed_by,
                        now,
                        details,
                    ),
                )
            return True
        except sqlite3.Error as e:
            logger.error(f"Failed to log wallet action: {e}")
            return False

    def get_wallet_actions(self, limit: int = 100) -> list:
        try:
            with sqlite3.connect(self.db_path) as conn:
                rows = conn.execute(
                    """
                    SELECT action_type, coin, purpose, amount, address, txid, performed_by, created_at, details
                    FROM wallet_actions
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            return [
                {
                    "action_type": row[0],
                    "coin": row[1],
                    "purpose": row[2],
                    "amount": row[3],
                    "address": row[4],
                    "txid": row[5],
                    "performed_by": row[6],
                    "created_at": row[7],
                    "details": row[8],
                }
                for row in rows
            ]
        except sqlite3.Error as e:
            logger.error(f"Failed to get wallet actions: {e}")
            return []
