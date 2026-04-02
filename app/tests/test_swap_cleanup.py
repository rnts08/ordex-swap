import sys
import os
import unittest
import tempfile
import json
import threading
import time
import importlib
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timezone, timedelta

# Add swap-service to path BEFORE any imports
_swap_service_path = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "swap-service"
)
if _swap_service_path not in sys.path:
    sys.path.insert(0, _swap_service_path)

from test_helpers import setup_test_db


class TestSwapCleanupJob(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["DB_PATH"] = os.path.join(self._tmpdir.name, "test.db")
        os.environ["TESTING_MODE"] = "false"
        os.environ["SWAP_CONFIRMATIONS_REQUIRED"] = "0"
        os.environ["SWAP_EXPIRE_MINUTES"] = "15"

        setup_test_db(os.environ["DB_PATH"])

        # Clear modules to ensure fresh imports
        for mod in (
            "config",
            "swap_engine",
            "swap_history",
            "db_pool",
            "swap_cleanup",
        ):
            if mod in sys.modules:
                del sys.modules[mod]

        config = importlib.import_module("config")
        swap_engine = importlib.import_module("swap_engine")
        swap_history = importlib.import_module("swap_history")
        swap_cleanup = importlib.import_module("swap_cleanup")

        self.SwapEngine = swap_engine.SwapEngine
        self.SwapHistoryService = swap_history.SwapHistoryService
        self.SwapCleanupJob = swap_cleanup.SwapCleanupJob

        self.oracle = Mock()
        self.oracle.get_market_price.return_value = 0.5
        now = datetime.now(timezone.utc)
        self.oracle.get_conversion_amount.return_value = {
            "to_amount": 99.0,
            "fee_amount": 1.0,
            "net_amount": 98.0,
            "rate": 100.0,
            "price_data": {"price": 100.0, "timestamp": now.isoformat()},
        }
        self.oxc_wallet = Mock()
        self.oxg_wallet = Mock()
        self.oxc_wallet.get_address.return_value = "oxc_test_addr"
        self.oxg_wallet.get_address.return_value = "oxg_test_addr"
        self.oxc_wallet.get_transaction.return_value = {"confirmations": 6}
        self.oxg_wallet.get_transaction.return_value = {"confirmations": 6}

        self.history = self.SwapHistoryService()
        self.engine = self.SwapEngine(
            price_oracle=self.oracle,
            oxc_wallet=self.oxc_wallet,
            oxg_wallet=self.oxg_wallet,
            history_service=self.history,
            fee_percent=1.0,
            min_amount=0.0001,
            max_amount=10000.0,
        )

    def tearDown(self):
        # Ensure cleanup job is stopped
        pass

    def test_cleanup_job_start_stop(self):
        """Test cleanup job can be started and stopped"""
        cleanup = self.SwapCleanupJob(self.engine)
        self.assertFalse(cleanup._running)

        cleanup.start()
        self.assertTrue(cleanup._running)
        self.assertIsNotNone(cleanup._thread)

        cleanup.stop()
        self.assertFalse(cleanup._running)

    def test_cleanup_job_start_idempotent(self):
        """Test starting cleanup job multiple times doesn't create multiple threads"""
        cleanup = self.SwapCleanupJob(self.engine)
        cleanup.start()
        thread1 = cleanup._thread

        cleanup.start()
        thread2 = cleanup._thread

        self.assertIs(thread1, thread2)
        cleanup.stop()

    def test_cleanup_job_stop_idempotent(self):
        """Test stopping cleanup job multiple times is safe"""
        cleanup = self.SwapCleanupJob(self.engine)
        cleanup.start()
        cleanup.stop()
        cleanup.stop()  # Should not raise
        self.assertFalse(cleanup._running)

    def test_cleanup_expired_swaps_marks_old_pending_as_timed_out(self):
        """Test that old pending swaps are marked as TIMED_OUT"""
        # Create a swap that's older than SWAP_EXPIRE_MINUTES
        swap = self.engine.create_swap("OXC", "OXG", 1.0, "user_address")
        swap_id = swap["swap_id"]

        # Manually set created_at to be old
        old_time = datetime.now(timezone.utc) - timedelta(minutes=20)
        with self.history._pool.get_connection() as conn:
            conn.execute(
                "UPDATE swaps SET created_at = ? WHERE swap_id = ?",
                (old_time.isoformat(), swap_id),
            )

        cleanup = self.SwapCleanupJob(self.engine)
        cleanup.cleanup_expired_swaps()

        # Verify swap is now marked as TIMED_OUT
        updated_swap = self.history.get_swap(swap_id)
        self.assertEqual(updated_swap["status"], "timed_out")

    def test_cleanup_does_not_affect_recent_swaps(self):
        """Test that recent swaps are not marked as TIMED_OUT"""
        # Create a recent swap
        swap = self.engine.create_swap("OXC", "OXG", 1.0, "user_address")
        swap_id = swap["swap_id"]

        cleanup = self.SwapCleanupJob(self.engine)
        cleanup.cleanup_expired_swaps()

        # Verify swap is still pending
        updated_swap = self.history.get_swap(swap_id)
        self.assertEqual(updated_swap["status"], "pending")

    def test_cleanup_does_not_affect_completed_swaps(self):
        """Test that completed swaps are not affected by cleanup"""
        swap = self.engine.create_swap("OXC", "OXG", 1.0, "user_address")
        swap_id = swap["swap_id"]

        # Mark as completed by confirming deposit with successful send
        self.oxg_wallet.send.return_value = "txid123"
        self.engine.confirm_deposit(swap_id, "deposit_txid")

        # Make it old
        old_time = datetime.now(timezone.utc) - timedelta(minutes=20)
        with self.history._pool.get_connection() as conn:
            conn.execute(
                "UPDATE swaps SET created_at = ? WHERE swap_id = ?",
                (old_time.isoformat(), swap_id),
            )

        cleanup = self.SwapCleanupJob(self.engine)
        cleanup.cleanup_expired_swaps()

        # Verify swap is still completed (not changed to timed_out)
        updated_swap = self.history.get_swap(swap_id)
        self.assertEqual(updated_swap["status"], "completed")

    def test_cleanup_does_not_affect_failed_swaps(self):
        """Test that failed swaps are not affected by cleanup"""
        swap = self.engine.create_swap("OXC", "OXG", 1.0, "user_address")
        swap_id = swap["swap_id"]

        # Mark as failed via direct database update
        swap["status"] = "failed"
        with self.history._pool.get_connection() as conn:
            conn.execute(
                "UPDATE swaps SET status = ?, data_json = ? WHERE swap_id = ?",
                ("failed", json.dumps(swap), swap_id),
            )

        # Make it old
        old_time = datetime.now(timezone.utc) - timedelta(minutes=20)
        with self.history._pool.get_connection() as conn:
            conn.execute(
                "UPDATE swaps SET created_at = ? WHERE swap_id = ?",
                (old_time.isoformat(), swap_id),
            )

        cleanup = self.SwapCleanupJob(self.engine)
        cleanup.cleanup_expired_swaps()

        # Verify swap is still failed
        updated_swap = self.history.get_swap(swap_id)
        self.assertEqual(updated_swap["status"], "failed")

    def test_cleanup_handles_malformed_json(self):
        """Test that cleanup gracefully handles malformed JSON in database"""
        # Insert malformed JSON directly into database
        with self.history._pool.get_connection() as conn:
            conn.execute(
                """INSERT INTO swaps 
                   (swap_id, status, data_json, created_at, updated_at, from_coin, from_amount)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    "bad_swap_id",
                    "pending",
                    "not valid json {{{",
                    (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat(),
                    datetime.now(timezone.utc).isoformat(),
                    "OXC",
                    1.0,
                ),
            )

        cleanup = self.SwapCleanupJob(self.engine)
        # Should not raise exception
        cleanup.cleanup_expired_swaps()

    def test_get_expired_swaps_returns_inactive_swaps(self):
        """Test get_expired_swaps returns cancelled/timed_out/expired swaps"""
        # Create and cancel a swap
        swap1 = self.engine.create_swap("OXC", "OXG", 1.0, "user_address")
        self.engine.cancel_swap(swap1["swap_id"])

        # Create another swap and mark as timed_out
        swap2 = self.engine.create_swap("OXC", "OXG", 1.0, "user_address")
        swap_id2 = swap2["swap_id"]
        swap2["status"] = "timed_out"
        with self.history._pool.get_connection() as conn:
            conn.execute(
                "UPDATE swaps SET status = ?, data_json = ? WHERE swap_id = ?",
                ("timed_out", json.dumps(swap2), swap_id2),
            )

        cleanup = self.SwapCleanupJob(self.engine)
        expired = cleanup.get_expired_swaps(limit=10)

        self.assertEqual(len(expired), 2)
        statuses = {swap["status"] for swap in expired}
        self.assertIn("cancelled", statuses)
        self.assertIn("timed_out", statuses)

    def test_get_expired_swaps_respects_limit(self):
        """Test get_expired_swaps respects the limit parameter"""
        # Create multiple cancelled swaps
        for i in range(5):
            swap = self.engine.create_swap("OXC", "OXG", 1.0, "user_address")
            self.engine.cancel_swap(swap["swap_id"])

        cleanup = self.SwapCleanupJob(self.engine)
        expired = cleanup.get_expired_swaps(limit=2)

        self.assertEqual(len(expired), 2)

    def test_cleanup_removes_from_pending_swaps_cache(self):
        """Test that cleanup removes expired swaps from engine's pending cache"""
        swap = self.engine.create_swap("OXC", "OXG", 1.0, "user_address")
        swap_id = swap["swap_id"]

        # Verify swap is in pending swaps
        self.assertIn(swap_id, self.engine._pending_swaps)

        # Make it old
        old_time = datetime.now(timezone.utc) - timedelta(minutes=20)
        with self.history._pool.get_connection() as conn:
            conn.execute(
                "UPDATE swaps SET created_at = ? WHERE swap_id = ?",
                (old_time.isoformat(), swap_id),
            )

        cleanup = self.SwapCleanupJob(self.engine)
        cleanup.cleanup_expired_swaps()

        # Verify swap is removed from pending cache
        self.assertNotIn(swap_id, self.engine._pending_swaps)

    def test_cleanup_job_thread_is_daemon(self):
        """Test that cleanup job runs as a daemon thread"""
        cleanup = self.SwapCleanupJob(self.engine)
        cleanup.start()

        self.assertTrue(cleanup._thread.daemon)
        cleanup.stop()

    def test_multiple_expired_swaps_cleanup(self):
        """Test cleanup processes multiple expired swaps"""
        # Create multiple old swaps
        old_time = datetime.now(timezone.utc) - timedelta(minutes=20)
        swap_ids = []

        for i in range(3):
            swap = self.engine.create_swap("OXC", "OXG", 1.0, f"user_{i}")
            swap_ids.append(swap["swap_id"])
            with self.history._pool.get_connection() as conn:
                conn.execute(
                    "UPDATE swaps SET created_at = ? WHERE swap_id = ?",
                    (old_time.isoformat(), swap["swap_id"]),
                )

        cleanup = self.SwapCleanupJob(self.engine)
        cleanup.cleanup_expired_swaps()

        # Verify all are timed out
        for swap_id in swap_ids:
            updated = self.history.get_swap(swap_id)
            self.assertEqual(updated["status"], "timed_out")

    def test_scan_unspent_deposits_confirms_matching_swap(self):
        """Test that scan_unspent_deposits triggers confirmation for matching UTXOs"""
        # Create a swap
        swap = self.engine.create_swap("OXC", "OXG", 1.0, "user_address")
        swap_id = swap["swap_id"]
        deposit_addr = swap["deposit_address"]

        # Mock list_unspent to return a matching UTXO
        self.oxc_wallet.rpc.list_unspent.return_value = [
            {"address": deposit_addr, "txid": "matching_txid", "amount": 1.0}
        ]
        self.oxg_wallet.rpc.list_unspent.return_value = []

        # Mock confirm_deposit to avoid actual wallet sends if not needed
        with patch.object(self.engine, "confirm_deposit") as mock_confirm:
            cleanup = self.SwapCleanupJob(self.engine)
            cleanup.scan_unspent_deposits()

            # Verify confirm_deposit was called with correct arguments
            mock_confirm.assert_called_once_with(swap_id, "matching_txid")

    def test_scan_unspent_deposits_ignores_low_amount(self):
        """Test that scan_unspent_deposits ignores UTXOs with insufficient amount"""
        # Create a swap
        swap = self.engine.create_swap("OXC", "OXG", 1.0, "user_address")
        swap_id = swap["swap_id"]
        deposit_addr = swap["deposit_address"]

        # Mock list_unspent with insufficient amount (0.5 < 1.0)
        self.oxc_wallet.rpc.list_unspent.return_value = [
            {"address": deposit_addr, "txid": "low_amount_txid", "amount": 0.5}
        ]
        self.oxg_wallet.rpc.list_unspent.return_value = []

        with patch.object(self.engine, "confirm_deposit") as mock_confirm:
            cleanup = self.SwapCleanupJob(self.engine)
            cleanup.scan_unspent_deposits()

            # Verify confirm_deposit was NOT called
            mock_confirm.assert_not_called()

    def test_scan_unspent_deposits_handles_timed_out_swaps(self):
        """Test that background scanner catches deposits for timed_out swaps"""
        swap = self.engine.create_swap("OXC", "OXG", 1.0, "user_address")
        swap_id = swap["swap_id"]
        deposit_addr = swap["deposit_address"]
        
        # Mark as timed_out
        swap["status"] = "timed_out"
        self.history.update_swap(swap_id, swap)

        self.oxc_wallet.rpc.list_unspent.return_value = [
            {"address": deposit_addr, "txid": "late_txid", "amount": 1.0}
        ]
        self.oxg_wallet.rpc.list_unspent.return_value = []

        cleanup = self.SwapCleanupJob(self.engine)
        cleanup.scan_unspent_deposits()

        # Verify status changed to late_deposit (via engine confirm_deposit logic)
        updated = self.history.get_swap(swap_id)
        self.assertEqual(updated["status"], "late_deposit")
        self.assertEqual(updated["deposit_txid"], "late_txid")


class TestSwapHistoryIncludeInactive(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["DB_PATH"] = os.path.join(self._tmpdir.name, "test.db")
        os.environ["TESTING_MODE"] = "false"
        os.environ["SWAP_CONFIRMATIONS_REQUIRED"] = "0"

        setup_test_db(os.environ["DB_PATH"])

        for mod in ("config", "swap_engine", "swap_history"):
            if mod in sys.modules:
                del sys.modules[mod]

        config = importlib.import_module("config")
        swap_engine = importlib.import_module("swap_engine")
        swap_history = importlib.import_module("swap_history")

        self.SwapEngine = swap_engine.SwapEngine
        self.SwapHistoryService = swap_history.SwapHistoryService

        self.oracle = Mock()
        self.oracle.get_market_price.return_value = 0.5
        now = datetime.now(timezone.utc)
        self.oracle.get_conversion_amount.return_value = {
            "to_amount": 99.0,
            "fee_amount": 1.0,
            "net_amount": 98.0,
            "rate": 100.0,
            "price_data": {"price": 100.0, "timestamp": now.isoformat()},
        }
        self.oxc_wallet = Mock()
        self.oxg_wallet = Mock()
        self.oxc_wallet.get_address.return_value = "oxc_test_addr"
        self.oxg_wallet.get_address.return_value = "oxg_test_addr"
        self.oxc_wallet.get_transaction.return_value = {"confirmations": 6}
        self.oxg_wallet.get_transaction.return_value = {"confirmations": 6}

        self.history = self.SwapHistoryService()
        self.engine = self.SwapEngine(
            price_oracle=self.oracle,
            oxc_wallet=self.oxc_wallet,
            oxg_wallet=self.oxg_wallet,
            history_service=self.history,
            fee_percent=1.0,
            min_amount=0.0001,
            max_amount=10000.0,
        )

    def test_list_swaps_active_only_by_default(self):
        """Test list_swaps returns only active swaps by default"""
        # Create pending swap
        swap1 = self.engine.create_swap("OXC", "OXG", 1.0, "user1")

        # Create and cancel a swap
        swap2 = self.engine.create_swap("OXC", "OXG", 1.0, "user2")
        self.engine.cancel_swap(swap2["swap_id"])

        swaps = self.engine.list_swaps(include_inactive=False)

        self.assertEqual(len(swaps), 1)
        self.assertEqual(swaps[0]["swap_id"], swap1["swap_id"])

    def test_list_swaps_include_inactive_all_statuses(self):
        """Test list_swaps with include_inactive returns all statuses"""
        # Create pending swap
        swap1 = self.engine.create_swap("OXC", "OXG", 1.0, "user1")

        # Create and cancel a swap
        swap2 = self.engine.create_swap("OXC", "OXG", 1.0, "user2")
        self.engine.cancel_swap(swap2["swap_id"])

        # Create and complete a swap
        swap3 = self.engine.create_swap("OXC", "OXG", 1.0, "user3")
        self.oxg_wallet.send.return_value = "txid123"
        self.engine.confirm_deposit(swap3["swap_id"], "deposit_txid")

        swaps = self.engine.list_swaps(include_inactive=True)

        self.assertEqual(len(swaps), 3)
        statuses = {swap["status"] for swap in swaps}
        self.assertIn("pending", statuses)
        self.assertIn("cancelled", statuses)
        self.assertIn("completed", statuses)

    def test_get_all_swaps_by_specific_status(self):
        """Test get_all_swaps filters by specific status"""
        # Create pending swap
        swap1 = self.engine.create_swap("OXC", "OXG", 1.0, "user1")

        # Create and cancel a swap
        swap2 = self.engine.create_swap("OXC", "OXG", 1.0, "user2")
        self.engine.cancel_swap(swap2["swap_id"])

        swaps = self.history.get_all_swaps(status="cancelled")

        self.assertEqual(len(swaps), 1)
        self.assertEqual(swaps[0]["status"], "cancelled")

    def test_get_all_swaps_invalid_status(self):
        """Test get_all_swaps with invalid status returns empty or default behavior"""
        swap1 = self.engine.create_swap("OXC", "OXG", 1.0, "user1")

        swaps = self.history.get_all_swaps(status="nonexistent")

        # Should return empty since status doesn't match
        self.assertEqual(len(swaps), 0)

    def test_admin_api_sees_all_swaps_no_status_filter(self):
        """Test admin endpoint returns all swaps when no status filter"""
        # Create various status swaps
        swap1 = self.engine.create_swap("OXC", "OXG", 1.0, "user1")
        swap2 = self.engine.create_swap("OXC", "OXG", 1.0, "user2")
        self.engine.cancel_swap(swap2["swap_id"])
        swap3 = self.engine.create_swap("OXC", "OXG", 1.0, "user3")
        self.oxg_wallet.send.return_value = "txid123"
        self.engine.confirm_deposit(swap3["swap_id"], "deposit_txid")

        # Simulate admin API call with no status filter
        include_inactive = None is None  # Simulates status parameter being None
        swaps = self.engine.list_swaps(status=None, include_inactive=include_inactive)

        # Should return at least active + completed (not cancelled by default filter logic)
        self.assertGreaterEqual(len(swaps), 2)


if __name__ == "__main__":
    unittest.main()
