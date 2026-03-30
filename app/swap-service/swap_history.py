import os
import json
import logging
import sqlite3
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from config import DATA_DIR, DB_PATH, DEFAULT_LIMIT
from db_pool import get_pool

logger = logging.getLogger(__name__)


class SwapHistoryService:
    def __init__(self, data_dir: str = None):
        self.data_dir = data_dir or DATA_DIR
        self.db_path = DB_PATH
        self._pool = get_pool(self.db_path)

        os.makedirs(self.data_dir, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        try:
            with self._pool.get_connection() as conn:
                conn.execute(
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
                    """
                )
        except sqlite3.Error as e:
            logger.error(f"Failed to initialize swap history db: {e}")

    def add_swap(self, swap: Dict[str, Any]) -> None:
        swap_id = swap.get("swap_id")
        if swap_id:
            now = datetime.now(timezone.utc).isoformat()
            created_at = swap.get("created_at") or now
            updated_at = swap.get("updated_at") or now
            try:
                with self._pool.get_connection() as conn:
                    conn.execute(
                        """
                        INSERT INTO swaps (
                            swap_id, status, data_json, created_at, updated_at, completed_at,
                            from_coin, from_amount
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(swap_id) DO UPDATE SET
                            status=excluded.status,
                            data_json=excluded.data_json,
                            updated_at=excluded.updated_at,
                            completed_at=excluded.completed_at,
                            from_coin=excluded.from_coin,
                            from_amount=excluded.from_amount
                        """,
                        (
                            swap_id,
                            "pending",
                            json.dumps(swap),
                            created_at,
                            updated_at,
                            swap.get("completed_at"),
                            swap.get("from_coin"),
                            swap.get("from_amount"),
                        ),
                    )
            except sqlite3.Error as e:
                logger.error(f"Failed to add swap: {e}")
            logger.info(f"Added swap to history: {swap_id}")

    def update_swap(self, swap_id: str, updates: Dict[str, Any]) -> None:
        existing = self.get_swap(swap_id)
        if not existing:
            return
        existing.update(updates)
        now = datetime.now(timezone.utc).isoformat()
        status = existing.get("status", "pending")
        completed_at = existing.get("completed_at")
        try:
            with self._pool.get_connection() as conn:
                conn.execute(
                    """
                    UPDATE swaps
                    SET status = ?,
                        data_json = ?,
                        updated_at = ?,
                        completed_at = ?,
                        from_coin = ?,
                        from_amount = ?
                    WHERE swap_id = ?
                    """,
                    (
                        status,
                        json.dumps(existing),
                        now,
                        completed_at,
                        existing.get("from_coin"),
                        existing.get("from_amount"),
                        swap_id,
                    ),
                )
        except sqlite3.Error as e:
            logger.error(f"Failed to update swap: {e}")

    def complete_swap(self, swap_id: str) -> None:
        swap = self.get_swap(swap_id)
        if not swap:
            return
        swap["completed_at"] = datetime.now(timezone.utc).isoformat()
        swap["status"] = "completed"
        try:
            with self._pool.get_connection() as conn:
                conn.execute(
                    """
                    UPDATE swaps
                    SET status = ?, data_json = ?, completed_at = ?, updated_at = ?
                    WHERE swap_id = ?
                    """,
                    (
                        "completed",
                        json.dumps(swap),
                        swap["completed_at"],
                        swap["completed_at"],
                        swap_id,
                    ),
                )
            logger.info(f"Completed swap: {swap_id}")
        except sqlite3.Error as e:
            logger.error(f"Failed to complete swap: {e}")

    def get_swap(self, swap_id: str) -> Optional[Dict[str, Any]]:
        try:
            with self._pool.get_connection() as conn:
                row = conn.execute(
                    "SELECT data_json FROM swaps WHERE swap_id = ?",
                    (swap_id,),
                ).fetchone()
            if not row:
                return None
            return json.loads(row[0])
        except (sqlite3.Error, json.JSONDecodeError) as e:
            logger.error(f"Failed to fetch swap: {e}")
            return None

    def get_pending_swaps(self) -> List[Dict[str, Any]]:
        try:
            with self._pool.get_connection() as conn:
                rows = conn.execute(
                    """
                    SELECT data_json FROM swaps
                    WHERE status IN (?, ?, ?, ?)
                    ORDER BY created_at DESC
                    """,
                    ("pending", "awaiting_deposit", "processing", "delayed"),
                ).fetchall()
            return [json.loads(r[0]) for r in rows]
        except (sqlite3.Error, json.JSONDecodeError) as e:
            logger.error(f"Failed to fetch pending swaps: {e}")
            return []

    def get_completed_swaps(self, limit: int = None) -> List[Dict[str, Any]]:
        limit = limit or DEFAULT_LIMIT
        if limit <= 0:
            return []
        try:
            with self._pool.get_connection() as conn:
                rows = conn.execute(
                    """
                    SELECT data_json FROM swaps
                    WHERE status = ?
                    ORDER BY completed_at DESC
                    LIMIT ?
                    """,
                    ("completed", limit),
                ).fetchall()
            return [json.loads(r[0]) for r in rows]
        except (sqlite3.Error, json.JSONDecodeError) as e:
            logger.error(f"Failed to fetch completed swaps: {e}")
            return []

    def get_all_swaps(
        self, status: str = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        if status == "pending":
            return self.get_pending_swaps()
        if status == "completed":
            return self.get_completed_swaps(limit)
        if status == "delayed":
            return self.get_swaps_by_statuses(["delayed"])
        pending = self.get_pending_swaps()
        completed = self.get_completed_swaps(max(limit - len(pending), 0))
        return pending + completed

    def get_swaps_by_statuses(self, statuses: List[str]) -> List[Dict[str, Any]]:
        if not statuses:
            return []
        placeholders = ", ".join("?" for _ in statuses)
        try:
            with self._pool.get_connection() as conn:
                rows = conn.execute(
                    f"SELECT data_json FROM swaps WHERE status IN ({placeholders})",
                    statuses,
                ).fetchall()
            return [json.loads(r[0]) for r in rows]
        except (sqlite3.Error, json.JSONDecodeError) as e:
            logger.error(f"Failed to fetch swaps by status: {e}")
            return []

    def get_stats(self) -> Dict[str, Any]:
        today_start = (
            datetime.now(timezone.utc)
            .replace(hour=0, minute=0, second=0, microsecond=0)
            .isoformat()
        )
        try:
            with self._pool.get_connection() as conn:
                total_swaps = conn.execute("SELECT COUNT(*) FROM swaps").fetchone()[0]
                pending_swaps = conn.execute(
                    "SELECT COUNT(*) FROM swaps WHERE status = ?", ("pending",)
                ).fetchone()[0]
                completed_today = conn.execute(
                    """
                    SELECT COUNT(*) FROM swaps
                    WHERE status = ? AND completed_at >= ?
                    """,
                    ("completed", today_start),
                ).fetchone()[0]
                total_volume_oxc = conn.execute(
                    """
                    SELECT COALESCE(SUM(from_amount), 0) FROM swaps
                    WHERE from_coin = ?
                    """,
                    ("OXC",),
                ).fetchone()[0]
                total_volume_oxg = conn.execute(
                    """
                    SELECT COALESCE(SUM(from_amount), 0) FROM swaps
                    WHERE from_coin = ?
                    """,
                    ("OXG",),
                ).fetchone()[0]
            return {
                "total_swaps": total_swaps,
                "pending_swaps": pending_swaps,
                "completed_today": completed_today,
                "total_volume_oxc": total_volume_oxc,
                "total_volume_oxg": total_volume_oxg,
            }
        except sqlite3.Error as e:
            logger.error(f"Failed to compute swap stats: {e}")
            return {
                "total_swaps": 0,
                "pending_swaps": 0,
                "completed_today": 0,
                "total_volume_oxc": 0,
                "total_volume_oxg": 0,
            }

    def get_financial_stats(self) -> Dict[str, Any]:
        stats = {
            "total_fees_collected": 0.0,
            "total_in": {"OXC": 0.0, "OXG": 0.0},
            "total_out": {"OXC": 0.0, "OXG": 0.0},
        }
        try:
            with self._pool.get_connection() as conn:
                rows = conn.execute(
                    "SELECT data_json FROM swaps WHERE status = ?",
                    ("completed",),
                ).fetchall()
            for row in rows:
                swap = json.loads(row[0])
                from_coin = swap.get("from_coin")
                to_coin = swap.get("to_coin")
                if from_coin in stats["total_in"]:
                    stats["total_in"][from_coin] += float(
                        swap.get("from_amount", 0) or 0
                    )
                if to_coin in stats["total_out"]:
                    stats["total_out"][to_coin] += float(swap.get("net_amount", 0) or 0)
                stats["total_fees_collected"] += float(swap.get("fee_amount", 0) or 0)
            return stats
        except (sqlite3.Error, json.JSONDecodeError) as e:
            logger.error(f"Failed to compute financial stats: {e}")
            return stats

    def get_status_counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        try:
            with self._pool.get_connection() as conn:
                rows = conn.execute(
                    "SELECT status, COUNT(*) FROM swaps GROUP BY status"
                ).fetchall()
            for status, count in rows:
                counts[status] = count
            return counts
        except sqlite3.Error as e:
            logger.error(f"Failed to compute status counts: {e}")
            return counts

    def search_swaps(self, query: str, field: str = "swap_id") -> List[Dict[str, Any]]:
        query = query.lower()
        results = []
        try:
            with self._pool.get_connection() as conn:
                rows = conn.execute("SELECT data_json FROM swaps").fetchall()
            for row in rows:
                swap = json.loads(row[0])
                if field in swap and query in str(swap[field]).lower():
                    results.append(swap)
            return results
        except (sqlite3.Error, json.JSONDecodeError) as e:
            logger.error(f"Failed to search swaps: {e}")
            return results
