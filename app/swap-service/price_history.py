import os
import logging
import threading
import time
import sqlite3
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from price_oracle import PriceOracle, PriceOracleError
from config import (
    DATA_DIR,
    DB_PATH,
    NESTEX_PRICE_TTL_SECONDS,
)

logger = logging.getLogger(__name__)


class PriceHistoryService:
    def __init__(
        self, oracle: PriceOracle, data_dir: str = None, history_file: str = None
    ):
        self.oracle = oracle
        self.data_dir = data_dir or DATA_DIR
        self.db_path = DB_PATH

        self._fetch_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._running = False

        os.makedirs(self.data_dir, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS price_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        ts_epoch REAL NOT NULL,
                        oxc_usdt REAL,
                        oxg_usdt REAL,
                        cross_rate REAL NOT NULL,
                        source TEXT
                    )
                    """
                )
        except sqlite3.Error as e:
            logger.error(f"Failed to initialize price history db: {e}")

    def fetch_and_record(self) -> Optional[Dict[str, Any]]:
        try:
            price_data = self.oracle.get_price("OXC", "OXG")

            now = datetime.now(timezone.utc)
            entry = {
                "timestamp": now.isoformat(),
                "ts_epoch": now.timestamp(),
                "oxc_usdt": price_data.get("oxc_usdt"),
                "oxg_usdt": price_data.get("oxg_usdt"),
                "cross_rate": price_data.get("price"),
                "source": price_data.get("source"),
            }

            try:
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute(
                        """
                        INSERT INTO price_history (
                            timestamp, ts_epoch, oxc_usdt, oxg_usdt, cross_rate, source
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            entry["timestamp"],
                            entry["ts_epoch"],
                            entry["oxc_usdt"],
                            entry["oxg_usdt"],
                            entry["cross_rate"],
                            entry["source"],
                        ),
                    )
            except sqlite3.Error as e:
                logger.error(f"Failed to insert price history: {e}")
            logger.info(
                f"Recorded: OXC/USDT={entry.get('oxc_usdt')}, OXG/USDT={entry.get('oxg_usdt')}, OXC/OXG={entry.get('cross_rate')}"
            )

            return entry

        except PriceOracleError as e:
            logger.error(f"Failed to fetch price: {e}")
            return None

    def get_latest(self) -> Optional[Dict[str, Any]]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                row = conn.execute(
                    """
                    SELECT timestamp, oxc_usdt, oxg_usdt, cross_rate, source
                    FROM price_history
                    ORDER BY ts_epoch DESC
                    LIMIT 1
                    """
                ).fetchone()
            if not row:
                return None
            return {
                "timestamp": row[0],
                "oxc_usdt": row[1],
                "oxg_usdt": row[2],
                "cross_rate": row[3],
                "source": row[4],
            }
        except sqlite3.Error as e:
            logger.error(f"Failed to read latest price: {e}")
            return None

    def start_background_fetch(self, interval_seconds: int = None) -> None:
        if self._running:
            logger.warning("Background price fetch already running")
            return

        interval = interval_seconds or NESTEX_PRICE_TTL_SECONDS
        self._running = True
        self._stop_event.clear()

        def fetch_loop():
            logger.info(f"Starting background price fetch (every {interval}s)")
            while not self._stop_event.is_set():
                self.fetch_and_record()
                self._stop_event.wait(interval)
            logger.info("Background price fetch stopped")

        self._fetch_thread = threading.Thread(target=fetch_loop, daemon=True)
        self._fetch_thread.start()
        logger.info("Background price fetch started")

    def stop_background_fetch(self) -> None:
        if not self._running:
            return

        logger.info("Stopping background price fetch...")
        self._stop_event.set()
        if self._fetch_thread:
            self._fetch_thread.join(timeout=5)
        self._running = False
        logger.info("Background price fetch stopped")

    def get_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        if limit <= 0:
            return []
        try:
            with sqlite3.connect(self.db_path) as conn:
                rows = conn.execute(
                    """
                    SELECT timestamp, oxc_usdt, oxg_usdt, cross_rate, source
                    FROM price_history
                    ORDER BY ts_epoch DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            history = [
                {
                    "timestamp": row[0],
                    "oxc_usdt": row[1],
                    "oxg_usdt": row[2],
                    "cross_rate": row[3],
                    "source": row[4],
                }
                for row in rows
            ]
            return list(reversed(history))
        except sqlite3.Error as e:
            logger.error(f"Failed to read price history: {e}")
            return []

    def get_latest_price(self) -> Optional[Dict[str, Any]]:
        latest = self.get_latest()
        return latest or self.fetch_and_record()

    def get_price_stats(self, hours: int = 24) -> Dict[str, Any]:
        cutoff = time.time() - (hours * 3600)
        try:
            with sqlite3.connect(self.db_path) as conn:
                row = conn.execute(
                    """
                    SELECT
                        COUNT(*) as count,
                        MIN(cross_rate) as min_rate,
                        MAX(cross_rate) as max_rate,
                        AVG(cross_rate) as avg_rate
                    FROM price_history
                    WHERE ts_epoch >= ?
                    """,
                    (cutoff,),
                ).fetchone()
                latest_row = conn.execute(
                    """
                    SELECT cross_rate FROM price_history
                    WHERE ts_epoch >= ?
                    ORDER BY ts_epoch DESC
                    LIMIT 1
                    """,
                    (cutoff,),
                ).fetchone()
            if not row or row[0] == 0:
                return {"count": 0, "hours": hours}
            return {
                "count": row[0],
                "hours": hours,
                "min": row[1],
                "max": row[2],
                "avg": row[3],
                "latest": latest_row[0] if latest_row else None,
            }
        except sqlite3.Error as e:
            logger.error(f"Failed to compute price stats: {e}")
            return {"count": 0, "hours": hours}
