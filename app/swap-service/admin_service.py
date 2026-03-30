import logging
import re
import sqlite3
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from werkzeug.security import generate_password_hash, check_password_hash

from config import DB_PATH, DEFAULT_LIMIT
from db_pool import get_pool
from structured_logging import StructuredLogger

logger = StructuredLogger(__name__)


def sanitize_string(value: str, max_length: int = 255) -> str:
    if not isinstance(value, str):
        return ""
    sanitized = re.sub(r"[^\w\s\-_.@]", "", value)
    return sanitized[:max_length].strip()


def sanitize_username(username: str) -> str:
    if not username or not isinstance(username, str):
        return ""
    return re.sub(r"[^a-zA-Z0-9_-]", "", username)[:64]


def validate_username(username: str) -> bool:
    if not username or not isinstance(username, str):
        return False
    return bool(re.match(r"^[a-zA-Z][a-zA-Z0-9_-]{2,63}$", username))


def validate_password(password: str) -> tuple[bool, str]:
    if not password or not isinstance(password, str):
        return False, "Password is required"
    if len(password) < 8:
        return False, "Password must be at least 8 characters"
    if len(password) > 128:
        return False, "Password too long"
    return True, ""


def sanitize_ip(ip: str) -> str:
    if not ip or not isinstance(ip, str):
        return ""
    ip = ip.strip()[:45]
    if re.match(r"^[a-zA-Z0-9:._-]+$", ip):
        return ip
    return ""


class AdminService:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or DB_PATH
        self._pool = get_pool(self.db_path)
        self._init_db()

    def _init_db(self) -> None:
        try:
            with self._pool.get_connection() as conn:
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
                    "INSERT OR IGNORE INTO app_settings (key, value, updated_at) VALUES (?, ?, ?)",
                    ("swap_fee_percent", "1.0", datetime.now(timezone.utc).isoformat()),
                )
                conn.execute(
                    "INSERT OR IGNORE INTO app_settings (key, value, updated_at) VALUES (?, ?, ?)",
                    (
                        "swap_confirmations_required",
                        "1",
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
                conn.execute(
                    "INSERT OR IGNORE INTO app_settings (key, value, updated_at) VALUES (?, ?, ?)",
                    ("swap_min_fee_OXC", "1.0", datetime.now(timezone.utc).isoformat()),
                )
                conn.execute(
                    "INSERT OR IGNORE INTO app_settings (key, value, updated_at) VALUES (?, ?, ?)",
                    ("swap_min_fee_OXG", "1.0", datetime.now(timezone.utc).isoformat()),
                )
                conn.execute(
                    "INSERT OR IGNORE INTO app_settings (key, value, updated_at) VALUES (?, ?, ?)",
                    (
                        "swap_min_amount",
                        "0.0001",
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
                conn.execute(
                    "INSERT OR IGNORE INTO app_settings (key, value, updated_at) VALUES (?, ?, ?)",
                    (
                        "swap_max_amount",
                        "10000.0",
                        datetime.now(timezone.utc).isoformat(),
                    ),
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
                        ip_address TEXT,
                        created_at TEXT,
                        details TEXT
                    )
                    """
                )
                conn.execute(
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
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS wallet_configs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        coin TEXT UNIQUE NOT NULL,
                        wallet_path TEXT NOT NULL,
                        wallet_name TEXT,
                        created_at TEXT,
                        updated_at TEXT
                    )
                    """
                )
        except sqlite3.Error as e:
            logger.error("Failed to initialize admin db", error=str(e))

    def has_admin_users(self) -> bool:
        try:
            with self._pool.get_connection() as conn:
                row = conn.execute("SELECT COUNT(*) FROM admin_users").fetchone()
                return (row[0] if row else 0) > 0
        except sqlite3.Error as e:
            logger.error("Failed to check admin users", error=str(e))
            return False

    def create_initial_admin(self, username: str, password: str) -> bool:
        if not self.has_admin_users():
            return self.create_admin(username, password)
        return False

    def log_audit(
        self,
        username: str,
        action: str,
        result: str,
        ip_address: str = None,
        details: str = None,
    ) -> None:
        try:
            now = datetime.now(timezone.utc).isoformat()
            with self._pool.get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO admin_audit_log (username, ip_address, action, result, details, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (username, ip_address, action, result, details, now),
                )
        except sqlite3.Error as e:
            logger.error("Failed to log audit", error=str(e))

    def get_audit_log(self, limit: int = 100) -> List[Dict[str, Any]]:
        try:
            with self._pool.get_connection() as conn:
                rows = conn.execute(
                    """
                    SELECT username, ip_address, action, result, details, created_at
                    FROM admin_audit_log
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            return [
                {
                    "username": row[0],
                    "ip_address": row[1],
                    "action": row[2],
                    "result": row[3],
                    "details": row[4],
                    "created_at": row[5],
                }
                for row in rows
            ]
        except sqlite3.Error as e:
            logger.error("Failed to fetch audit log", error=str(e))
            return []

    def verify_credentials(
        self, username: str, password: str, ip_address: str = None
    ) -> bool:
        username = sanitize_username(username)
        if not username:
            return False

        try:
            with self._pool.get_connection() as conn:
                row = conn.execute(
                    "SELECT id, password_hash FROM admin_users WHERE username = ?",
                    (username,),
                ).fetchone()
            if not row:
                return False
            admin_id, password_hash = row
            if not check_password_hash(password_hash, password):
                self.log_audit(
                    username, "login", "failed", ip_address, "Invalid password"
                )
                return False
            now = datetime.now(timezone.utc).isoformat()
            with self._pool.get_connection() as conn:
                conn.execute(
                    "UPDATE admin_users SET last_login_at = ?, updated_at = ? WHERE id = ?",
                    (now, now, admin_id),
                )
            self.log_audit(username, "login", "success", ip_address)
            return True
        except sqlite3.Error as e:
            logger.error("Failed to verify admin credentials", error=str(e))
            return False

    def get_wallet_path(self, coin: str) -> Optional[str]:
        """Get wallet path for a coin from database."""
        try:
            with self._pool.get_connection() as conn:
                row = conn.execute(
                    "SELECT wallet_path FROM wallet_configs WHERE coin = ?",
                    (coin,),
                ).fetchone()
                return row[0] if row else None
        except sqlite3.Error as e:
            logger.error(f"Failed to get wallet path for {coin}", error=str(e))
            return None

    def set_wallet_config(
        self, coin: str, wallet_path: str, wallet_name: str = None
    ) -> bool:
        """Store wallet configuration for a coin."""
        try:
            now = datetime.now(timezone.utc).isoformat()
            with self._pool.get_connection() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO wallet_configs
                    (coin, wallet_path, wallet_name, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (coin, wallet_path, wallet_name, now, now),
                )
            return True
        except sqlite3.Error as e:
            logger.error(f"Failed to set wallet config for {coin}", error=str(e))
            return False

    def list_wallet_configs(self) -> List[Dict[str, Any]]:
        """List all wallet configurations."""
        try:
            with self._pool.get_connection() as conn:
                rows = conn.execute(
                    "SELECT coin, wallet_path, wallet_name, updated_at FROM wallet_configs"
                ).fetchall()
            return [
                {
                    "coin": row[0],
                    "wallet_path": row[1],
                    "wallet_name": row[2],
                    "updated_at": row[3],
                }
                for row in rows
            ]
        except sqlite3.Error as e:
            logger.error("Failed to list wallet configs", error=str(e))
            return []

    def get_or_create_wallet_address(
        self, coin: str, purpose: str, address_generator
    ) -> Optional[str]:
        try:
            with self._pool.get_connection() as conn:
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
            logger.error("Failed to get or create admin wallet", error=str(e))
            return None

    def rotate_wallet_address(
        self, coin: str, purpose: str, address_generator
    ) -> Optional[str]:
        try:
            address = address_generator()
            now = datetime.now(timezone.utc).isoformat()
            with self._pool.get_connection() as conn:
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
            logger.error("Failed to rotate admin wallet", error=str(e))
            return None

    def list_wallets(self) -> Dict[str, Dict[str, Any]]:
        wallets: Dict[str, Dict[str, Any]] = {}
        try:
            with self._pool.get_connection() as conn:
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
            logger.error("Failed to list admin wallets", error=str(e))
        return wallets

    def create_admin(
        self,
        username: str,
        password: str,
        ip_address: str = None,
        created_by: str = None,
    ) -> bool:
        username = sanitize_username(username)
        if not validate_username(username):
            return False

        valid, msg = validate_password(password)
        if not valid:
            return False

        try:
            now = datetime.now(timezone.utc).isoformat()
            with self._pool.get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO admin_users (username, password_hash, created_at, updated_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (username, generate_password_hash(password), now, now),
                )
            self.log_audit(
                created_by or username,
                "create_admin",
                "success",
                ip_address,
                f"Created user: {username}",
            )
            return True
        except sqlite3.IntegrityError:
            self.log_audit(
                created_by or username,
                "create_admin",
                "failed",
                ip_address,
                f"Username already exists: {username}",
            )
            return False
        except sqlite3.Error as e:
            logger.error("Failed to create admin user", error=str(e))
            return False

    def list_admins(self) -> List[Dict[str, Any]]:
        try:
            with self._pool.get_connection() as conn:
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
            logger.error("Failed to list admin users", error=str(e))
            return []

    def update_password(
        self,
        username: str,
        current_password: str,
        new_password: str,
        ip_address: str = None,
    ) -> bool:
        username = sanitize_username(username)
        if not username:
            return False

        valid, msg = validate_password(new_password)
        if not valid:
            return False

        if not self.verify_credentials(username, current_password, ip_address):
            self.log_audit(
                username,
                "change_password",
                "failed",
                ip_address,
                "Invalid current password",
            )
            return False

        try:
            now = datetime.now(timezone.utc).isoformat()
            with self._pool.get_connection() as conn:
                conn.execute(
                    """
                    UPDATE admin_users
                    SET password_hash = ?, updated_at = ?
                    WHERE username = ?
                    """,
                    (generate_password_hash(new_password), now, username),
                )
            self.log_audit(username, "change_password", "success", ip_address)
            return True
        except sqlite3.Error as e:
            logger.error("Failed to update admin password", error=str(e))
            return False

    def get_swaps_enabled(self) -> bool:
        try:
            with self._pool.get_connection() as conn:
                row = conn.execute(
                    "SELECT value FROM app_settings WHERE key = ?",
                    ("swaps_enabled",),
                ).fetchone()
            return row[0] == "true" if row else True
        except sqlite3.Error as e:
            logger.error("Failed to get swaps_enabled", error=str(e))
            return True

    def set_swaps_enabled(
        self, enabled: bool, username: str = None, ip_address: str = None
    ) -> bool:
        try:
            now = datetime.now(timezone.utc).isoformat()
            with self._pool.get_connection() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO app_settings (key, value, updated_at) VALUES (?, ?, ?)",
                    ("swaps_enabled", "true" if enabled else "false", now),
                )
            self.log_audit(
                username or "system",
                "set_swaps_enabled",
                "success",
                ip_address,
                f"enabled={enabled}",
            )
            return True
        except sqlite3.Error as e:
            logger.error("Failed to set swaps_enabled", error=str(e))
            return False

    def get_swap_fee_percent(self) -> float:
        try:
            with self._pool.get_connection() as conn:
                row = conn.execute(
                    "SELECT value FROM app_settings WHERE key = ?",
                    ("swap_fee_percent",),
                ).fetchone()
            if row:
                return float(row[0])
            return None
        except sqlite3.Error as e:
            logger.error("Failed to get swap_fee_percent", error=str(e))
            return None

    def set_swap_fee_percent(
        self, fee_percent: float, username: str = None, ip_address: str = None
    ) -> bool:
        try:
            fee_percent = float(fee_percent)
            if fee_percent < 0 or fee_percent > 100:
                return False
        except (ValueError, TypeError):
            return False
        try:
            now = datetime.now(timezone.utc).isoformat()
            with self._pool.get_connection() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO app_settings (key, value, updated_at) VALUES (?, ?, ?)",
                    ("swap_fee_percent", str(fee_percent), now),
                )
            self.log_audit(
                username or "system",
                "set_swap_fee_percent",
                "success",
                ip_address,
                f"fee_percent={fee_percent}",
            )
            return True
        except sqlite3.Error as e:
            logger.error("Failed to set swap_fee_percent", error=str(e))
            return False

    def get_swap_confirmations_required(self) -> int:
        try:
            with self._pool.get_connection() as conn:
                row = conn.execute(
                    "SELECT value FROM app_settings WHERE key = ?",
                    ("swap_confirmations_required",),
                ).fetchone()
            if row:
                return int(row[0])
            return None
        except sqlite3.Error as e:
            logger.error("Failed to get swap_confirmations_required", error=str(e))
            return None

    def set_swap_confirmations_required(
        self, confirmations: int, username: str = None, ip_address: str = None
    ) -> bool:
        try:
            confirmations = int(confirmations)
            if confirmations < 0:
                return False
        except (ValueError, TypeError):
            return False
        try:
            now = datetime.now(timezone.utc).isoformat()
            with self._pool.get_connection() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO app_settings (key, value, updated_at) VALUES (?, ?, ?)",
                    ("swap_confirmations_required", str(confirmations), now),
                )
            self.log_audit(
                username or "system",
                "set_swap_confirmations_required",
                "success",
                ip_address,
                f"confirmations={confirmations}",
            )
            return True
        except sqlite3.Error as e:
            logger.error("Failed to set swap_confirmations_required", error=str(e))
            return False

    def get_swap_min_fee(self, coin: str) -> float:
        try:
            with self._pool.get_connection() as conn:
                row = conn.execute(
                    "SELECT value FROM app_settings WHERE key = ?",
                    (f"swap_min_fee_{coin.upper()}",),
                ).fetchone()
            if row:
                return float(row[0])
            return None
        except sqlite3.Error as e:
            logger.error(f"Failed to get swap_min_fee_{coin}", error=str(e))
            return None

    def set_swap_min_fee(
        self, coin: str, min_fee: float, username: str = None, ip_address: str = None
    ) -> bool:
        coin = sanitize_string(coin, 10).upper()
        if coin not in ("OXC", "OXG"):
            return False
        try:
            min_fee = float(min_fee)
            if min_fee < 0:
                return False
        except (ValueError, TypeError):
            return False
        try:
            now = datetime.now(timezone.utc).isoformat()
            with self._pool.get_connection() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO app_settings (key, value, updated_at) VALUES (?, ?, ?)",
                    (f"swap_min_fee_{coin}", str(min_fee), now),
                )
            self.log_audit(
                username or "system",
                "set_swap_min_fee",
                "success",
                ip_address,
                f"coin={coin},min_fee={min_fee}",
            )
            return True
        except sqlite3.Error as e:
            logger.error(f"Failed to set swap_min_fee_{coin}", error=str(e))
            return False

    def get_all_settings(self) -> Dict[str, Any]:
        settings = {}
        try:
            with self._pool.get_connection() as conn:
                rows = conn.execute("SELECT key, value FROM app_settings").fetchall()
            for key, value in rows:
                if value == "true":
                    settings[key] = True
                elif value == "false":
                    settings[key] = False
                else:
                    try:
                        settings[key] = float(value)
                    except ValueError:
                        settings[key] = value
        except sqlite3.Error as e:
            logger.error("Failed to get all settings", error=str(e))
        return settings

    def get_swap_min_amount(self) -> float:
        try:
            with self._pool.get_connection() as conn:
                row = conn.execute(
                    "SELECT value FROM app_settings WHERE key = ?",
                    ("swap_min_amount",),
                ).fetchone()
            if row:
                return float(row[0])
            return None
        except sqlite3.Error as e:
            logger.error("Failed to get swap_min_amount", error=str(e))
            return None

    def set_swap_min_amount(
        self, min_amount: float, username: str = None, ip_address: str = None
    ) -> bool:
        try:
            min_amount = float(min_amount)
            if min_amount < 0:
                return False
        except (ValueError, TypeError):
            return False
        try:
            now = datetime.now(timezone.utc).isoformat()
            with self._pool.get_connection() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO app_settings (key, value, updated_at) VALUES (?, ?, ?)",
                    ("swap_min_amount", str(min_amount), now),
                )
            self.log_audit(
                username or "system",
                "set_swap_min_amount",
                "success",
                ip_address,
                f"min_amount={min_amount}",
            )
            return True
        except sqlite3.Error as e:
            logger.error("Failed to set swap_min_amount", error=str(e))
            return False

    def get_swap_max_amount(self) -> float:
        try:
            with self._pool.get_connection() as conn:
                row = conn.execute(
                    "SELECT value FROM app_settings WHERE key = ?",
                    ("swap_max_amount",),
                ).fetchone()
            if row:
                return float(row[0])
            return None
        except sqlite3.Error as e:
            logger.error("Failed to get swap_max_amount", error=str(e))
            return None

    def set_swap_max_amount(
        self, max_amount: float, username: str = None, ip_address: str = None
    ) -> bool:
        try:
            max_amount = float(max_amount)
            if max_amount < 0:
                return False
        except (ValueError, TypeError):
            return False
        try:
            now = datetime.now(timezone.utc).isoformat()
            with self._pool.get_connection() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO app_settings (key, value, updated_at) VALUES (?, ?, ?)",
                    ("swap_max_amount", str(max_amount), now),
                )
            self.log_audit(
                username or "system",
                "set_swap_max_amount",
                "success",
                ip_address,
                f"max_amount={max_amount}",
            )
            return True
        except sqlite3.Error as e:
            logger.error("Failed to set swap_max_amount", error=str(e))
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
        ip_address: str = None,
        details: str = None,
    ) -> bool:
        try:
            now = datetime.now(timezone.utc).isoformat()
            with self._pool.get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO wallet_actions 
                    (action_type, coin, purpose, amount, address, txid, performed_by, ip_address, created_at, details)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        action_type,
                        coin,
                        purpose,
                        amount,
                        address,
                        txid,
                        performed_by,
                        ip_address,
                        now,
                        details,
                    ),
                )
            logger.info(
                f"Wallet action logged",
                action_type=action_type,
                coin=coin,
                purpose=purpose,
                performed_by=performed_by,
                ip_address=ip_address,
            )
            return True
        except sqlite3.Error as e:
            logger.error("Failed to log wallet action", error=str(e))
            return False

    def get_wallet_actions(self, limit: int = None) -> list:
        limit = limit or DEFAULT_LIMIT
        try:
            with self._pool.get_connection() as conn:
                rows = conn.execute(
                    """
                    SELECT action_type, coin, purpose, amount, address, txid, performed_by, ip_address, created_at, details
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
                    "ip_address": row[7],
                    "created_at": row[8],
                    "details": row[9],
                }
                for row in rows
            ]
        except sqlite3.Error as e:
            logger.error("Failed to get wallet actions", error=str(e))
            return []
