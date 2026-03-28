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
    def __init__(self, oracle: PriceOracle, data_dir: str = None):
        self.oracle = oracle
        self.data_dir = data_dir or DATA_DIR
        self.db_path = DB_PATH

        self._fetch_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._running = False
        self._backfilled = False

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

    def has_24h_coverage(self, hours: int = 24) -> bool:
        cutoff = time.time() - (hours * 3600)
        try:
            with sqlite3.connect(self.db_path) as conn:
                row = conn.execute(
                    """
                    SELECT COUNT(*), MIN(ts_epoch), MAX(ts_epoch)
                    FROM price_history
                    WHERE ts_epoch >= ?
                    """,
                    (cutoff,),
                ).fetchone()
            if not row or row[0] == 0:
                return False
            count, min_ts, max_ts = row
            if count < hours:
                return False
            if min_ts is None or max_ts is None:
                return False
            return (max_ts - min_ts) >= ((hours - 1) * 3600)
        except sqlite3.Error as e:
            logger.error(f"Failed checking price history coverage: {e}")
            return False

    def ensure_backfill(self, hours: int = 24) -> None:
        if self.has_24h_coverage(hours):
            logger.info(
                "Price history already has %sh coverage; skipping backfill", hours
            )
            return
        logger.info("Price history missing %sh coverage; starting backfill", hours)
        self.backfill_from_tradebook(hours=hours)

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
        self._interval_seconds = interval
        self._last_fetch_at = None
        self._stop_event.clear()

        # Seed one entry so graphs have data quickly.
        self.fetch_and_record()

        def fetch_loop():
            logger.info(f"Starting background price fetch (every {interval}s)")
            while not self._stop_event.is_set():
                self.fetch_and_record()
                self._last_fetch_at = datetime.now(timezone.utc).isoformat()
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

    def get_background_status(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "last_fetch_at": self._last_fetch_at,
            "interval_seconds": getattr(self, "_interval_seconds", None),
        }

    def get_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        if limit <= 0:
            return []
        try:
            with sqlite3.connect(self.db_path) as conn:
                rows = conn.execute(
                    """
                    SELECT 
                        datetime((strftime('%s', timestamp) / 3600) * 3600, 'unixepoch') as hour_bucket,
                        AVG(oxc_usdt) as oxc_usdt,
                        AVG(oxg_usdt) as oxg_usdt,
                        AVG(cross_rate) as cross_rate
                    FROM price_history
                    GROUP BY hour_bucket
                    ORDER BY hour_bucket DESC
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
                    "source": "hourly_avg",
                }
                for row in rows
            ]
            if not self._backfilled:
                has_ticker = any(
                    h["source"] in ("nestex_ticker", "nestex_tradebook", "hourly_avg")
                    for h in history
                )
                if not history or not has_ticker:
                    self.backfill_from_tradebook(hours=24)
                    self._backfilled = True
                    return self.get_history(limit)
            return list(reversed(history))
        except sqlite3.Error as e:
            logger.error(f"Failed to read price history: {e}")
            return []

    def get_latest_price(self) -> Optional[Dict[str, Any]]:
        latest = self.get_latest()
        return latest or self.fetch_and_record()

    def backfill_from_tradebook(self, hours: int = 24, max_pages: int = 6) -> None:
        if hours <= 0:
            return
        logger.info(
            "Backfill requested from tradebook: hours=%s max_pages=%s",
            hours,
            max_pages,
        )
        now_ms = int(time.time() * 1000)
        cutoff_ms = now_ms - (hours * 3600 * 1000)

        def collect_trades(ticker_id: str) -> List[Dict[str, Any]]:
            trades: List[Dict[str, Any]] = []
            for page in range(1, max_pages + 1):
                try:
                    payload = self.oracle.get_tradebook(ticker_id, page=page)
                    page_trades = payload.get("data", [])
                except Exception as e:
                    logger.warning(
                        f"Failed tradebook fetch {ticker_id} page {page}: {e}"
                    )
                    break
                if not page_trades:
                    break
                trades.extend(page_trades)
                oldest = min(
                    (t.get("timestamp", now_ms) for t in page_trades), default=now_ms
                )
                if oldest < cutoff_ms:
                    break
            return trades

        oxc_trades = collect_trades("OXC_USDT")
        oxg_trades = collect_trades("OXG_USDT")

        if not oxc_trades or not oxg_trades:
            logger.warning("Insufficient tradebook data for backfill")
            return

        oxc_buckets = [[] for _ in range(hours)]
        oxg_buckets = [[] for _ in range(hours)]

        def bucket_trade(trade, buckets):
            ts = int(trade.get("timestamp", 0))
            if ts < cutoff_ms or ts > now_ms:
                return
            idx = int((ts - cutoff_ms) // 3600000)
            if 0 <= idx < hours:
                price = float(trade.get("price", 0) or 0)
                if price > 0:
                    buckets[idx].append(price)

        for t in oxc_trades:
            bucket_trade(t, oxc_buckets)
        for t in oxg_trades:
            bucket_trade(t, oxg_buckets)

        entries = []
        for i in range(hours):
            if not oxc_buckets[i] or not oxg_buckets[i]:
                continue
            oxc_avg = sum(oxc_buckets[i]) / len(oxc_buckets[i])
            oxg_avg = sum(oxg_buckets[i]) / len(oxg_buckets[i])
            if oxg_avg <= 0:
                continue
            cross_rate = oxc_avg / oxg_avg
            ts_epoch = (cutoff_ms // 1000) + (i * 3600)
            timestamp = datetime.fromtimestamp(ts_epoch, tz=timezone.utc).isoformat()
            entries.append(
                (
                    timestamp,
                    ts_epoch,
                    oxc_avg,
                    oxg_avg,
                    cross_rate,
                    "nestex_tradebook",
                )
            )

        if not entries:
            logger.warning("No backfill entries generated from tradebook")
            return

        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    DELETE FROM price_history
                    WHERE ts_epoch BETWEEN ? AND ?
                    AND source IN ('fallback', 'nestex_cross_usdt')
                    """,
                    (cutoff_ms / 1000, now_ms / 1000),
                )
                conn.executemany(
                    """
                    INSERT INTO price_history (
                        timestamp, ts_epoch, oxc_usdt, oxg_usdt, cross_rate, source
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    entries,
                )
            logger.info(f"Backfilled {len(entries)} price points from tradebook")
        except sqlite3.Error as e:
            logger.error(f"Failed to backfill price history: {e}")

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
