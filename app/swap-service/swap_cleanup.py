import logging
import threading
import json
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any

from config import SWAP_EXPIRE_MINUTES
from db_pool import get_pool
from swap_engine import SwapEngine, SwapStatus
from swap_history import SwapHistoryService

logger = logging.getLogger(__name__)


class SwapCleanupJob:
    def __init__(self, swap_engine: SwapEngine, db_path: str = None):
        self.swap_engine = swap_engine
        self.db_path = db_path
        self._running = False
        self._thread = None
        self.cleanup_interval = 300  # 5 minutes

    def start(self):
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._thread.start()
        logger.info("Swap cleanup job started")

    def stop(self):
        if not self._running:
            return

        self._running = False
        if self._thread:
            self._thread.join()
        logger.info("Swap cleanup job stopped")

    def _cleanup_loop(self):
        while self._running:
            try:
                self.cleanup_expired_swaps()
            except Exception as e:
                logger.error(f"Error in swap cleanup: {e}")
            # Wait for next interval
            for _ in range(self.cleanup_interval):
                if not self._running:
                    break
                import time

                time.sleep(1)

    def cleanup_expired_swaps(self):
        """Find and mark expired swaps as TIMED_OUT"""
        try:
            from admin_service import AdminService
            admin_svc = AdminService(self.db_path)
            db_expire_mins = admin_svc.get_swap_expire_minutes()
            expire_mins = db_expire_mins if db_expire_mins is not None else SWAP_EXPIRE_MINUTES

            with self.swap_engine.history._pool.get_connection() as conn:
                # Find swaps that are older than expire_mins
                expire_threshold = datetime.now(timezone.utc) - timedelta(
                    minutes=expire_mins
                )
                threshold_str = expire_threshold.isoformat()

                # Find pending swaps that have expired
                rows = conn.execute(
                    """
                    SELECT swap_id, data_json 
                    FROM swaps 
                    WHERE status IN ('pending', 'awaiting_deposit', 'processing')
                    AND created_at < ?
                    """,
                    (threshold_str,),
                ).fetchall()

                expired_count = 0
                for swap_id, data_json in rows:
                    try:
                        swap_data = json.loads(data_json)
                        if swap_data.get("status") in [
                            "pending",
                            "awaiting_deposit",
                            "processing",
                        ]:
                            # Update swap status to timed_out
                            swap_data["status"] = SwapStatus.TIMED_OUT.value
                            swap_data["updated_at"] = datetime.now(timezone.utc).isoformat()
                            
                            conn.execute(
                                """
                                UPDATE swaps 
                                SET status = ?, data_json = ?, updated_at = ? 
                                WHERE swap_id = ?
                                """,
                                (
                                    SwapStatus.TIMED_OUT.value,
                                    json.dumps(swap_data),
                                    datetime.now(timezone.utc).isoformat(),
                                    swap_id,
                                ),
                            )

                            # Remove from engine's pending swaps if it's there
                            if swap_id in self.swap_engine._pending_swaps:
                                del self.swap_engine._pending_swaps[swap_id]

                            expired_count += 1
                    except Exception as e:
                        logger.error(f"Error processing expired swap {swap_id}: {e}")

                if expired_count > 0:
                    logger.info(f"Marked {expired_count} swaps as TIMED_OUT")

        except Exception as e:
            logger.error(f"Error in cleanup_expired_swaps: {e}")

    def get_expired_swaps(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recently expired swaps for admin display"""
        try:
            with self.swap_engine.history._pool.get_connection() as conn:
                rows = conn.execute(
                    """
                    SELECT data_json FROM swaps 
                    WHERE status IN ('cancelled', 'expired', 'timed_out')
                    ORDER BY updated_at DESC 
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()

                swaps = []
                for row in rows:
                    try:
                        data_json = row[0]
                        swaps.append(json.loads(data_json))
                    except (json.JSONDecodeError, Exception) as e:
                        logger.warning(f"Failed to parse swap data: {e}")
                        continue

                return swaps
        except Exception as e:
            logger.error(f"Error getting expired swaps: {e}")
            return []
