import os
import json
import logging
import sqlite3
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from config import DATA_DIR, DB_PATH, DEFAULT_LIMIT, STAT_INCLUDED_STATUSES
from db_pool import get_pool

logger = logging.getLogger(__name__)


class SwapHistoryService:
    def __init__(self, data_dir: str = None):
        self.data_dir = data_dir or DATA_DIR
        self.db_path = DB_PATH
        self._pool = get_pool(self.db_path)

        os.makedirs(self.data_dir, exist_ok=True)

    def _log_audit(
        self,
        swap_id: str,
        new_status: str,
        old_status: str = None,
        details: str = None,
        performed_by: str = "system",
    ) -> None:
        try:
            now = datetime.now(timezone.utc).isoformat()
            with self._pool.get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO swap_audit_log (swap_id, old_status, new_status, details, performed_by, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (swap_id, old_status, new_status, details, performed_by, now),
                )
        except sqlite3.Error as e:
            # We don't want to crash the main flow if auditing fails, but we should log it
            logger.error(f"Failed to log swap audit for {swap_id}: {e}")

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
            
            self._log_audit(swap_id, "pending", details="Initial swap creation")
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
        
        if existing.get("status") != status:
            self._log_audit(swap_id, status, old_status=existing.get("status"), details="Swap status update")

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
        
        self._log_audit(swap_id, "completed", old_status=swap.get("status"), details="Swap settlement complete")

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
            logger.error(f"Failed to fetch swap {swap_id}: {e}")
            return None

    def get_swap_by_address(self, address: str) -> Optional[Dict[str, Any]]:
        """Find the most recent swap associated with a deposit address."""
        if not address:
            return None
        try:
            with self._pool.get_connection() as conn:
                # Search within data_json for the address
                # Since address is unique per swap (usually), we look for a match
                rows = conn.execute(
                    "SELECT data_json FROM swaps WHERE data_json LIKE ?",
                    (f'%"deposit_address": "{address}"%',),
                ).fetchall()
            if not rows:
                return None
            
            # If multiple swaps use the same address (rare but possible if re-used after long time),
            # pick the most recent one.
            swaps = [json.loads(r[0]) for r in rows]
            swaps.sort(key=lambda s: s.get("created_at", ""), reverse=True)
            return swaps[0]
        except (sqlite3.Error, json.JSONDecodeError) as e:
            logger.error(f"Failed to fetch swap by address {address}: {e}")
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
        self, status: str = None, limit: int = 100, include_inactive: bool = False
    ) -> List[Dict[str, Any]]:
        if status:
            if status == "pending":
                return self.get_pending_swaps()
            if status == "completed":
                return self.get_completed_swaps(limit)
            if status == "delayed":
                return self.get_swaps_by_statuses(["delayed"])
            if status in ["cancelled", "expired", "timed_out"]:
                return self.get_swaps_by_statuses([status])
            return self.get_swaps_by_statuses([status])

        if include_inactive:
            # Return all swaps (including cancelled, timed_out, expired, etc.)
            try:
                with self._pool.get_connection() as conn:
                    rows = conn.execute(
                        "SELECT data_json FROM swaps ORDER BY created_at DESC LIMIT ?",
                        (limit,),
                    ).fetchall()
                return [json.loads(r[0]) for r in rows]
            except (sqlite3.Error, json.JSONDecodeError) as e:
                logger.error(f"Failed to fetch all swaps: {e}")
                return []

        # Active only: pending + completed (excludes cancelled, timed_out, expired)
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
        statuses = STAT_INCLUDED_STATUSES
        placeholders = ", ".join("?" for _ in statuses)

        try:
            with self._pool.get_connection() as conn:
                # Count "funded" swaps based on configured statuses
                total_swaps = conn.execute(
                    f"SELECT COUNT(*) FROM swaps WHERE status IN ({placeholders})", 
                    statuses
                ).fetchone()[0]
                
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
                    f"""
                    SELECT COALESCE(SUM(from_amount), 0) FROM swaps
                    WHERE from_coin = ? AND status IN ({placeholders})
                    """,
                    ("OXC", *statuses),
                ).fetchone()[0]
                
                total_volume_oxg = conn.execute(
                    f"""
                    SELECT COALESCE(SUM(from_amount), 0) FROM swaps
                    WHERE from_coin = ? AND status IN ({placeholders})
                    """,
                    ("OXG", *statuses),
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
        statuses = STAT_INCLUDED_STATUSES
        placeholders = ", ".join("?" for _ in statuses)

        try:
            with self._pool.get_connection() as conn:
                rows = conn.execute(
                    f"SELECT data_json FROM swaps WHERE status IN ({placeholders})",
                    statuses,
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
