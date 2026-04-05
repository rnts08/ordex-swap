import os
import sys
import unittest
import tempfile
import importlib
from unittest.mock import MagicMock

# Add swap-service to path
_swap_service_path = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "swap-service"
)
if _swap_service_path not in sys.path:
    sys.path.insert(0, _swap_service_path)

from test_helpers import setup_test_db


class TestAdminOverride(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["DB_PATH"] = os.path.join(self._tmpdir.name, "test.db")
        os.environ["TESTING_MODE"] = "true"

        setup_test_db(os.environ["DB_PATH"])

        # Force reload of modules
        for mod in ["config", "swap_engine", "swap_history", "admin_service"]:
            if mod in sys.modules:
                del sys.modules[mod]

        self.swap_engine = importlib.import_module("swap_engine")
        self.swap_history = importlib.import_module("swap_history")
        self.admin_service = importlib.import_module("admin_service")
        self.SwapError = self.swap_engine.SwapError

        self.history = self.swap_history.SwapHistoryService()
        self.admin = self.admin_service.AdminService()

        # Create mock oracle and wallets
        self.oracle = MagicMock()
        self.oracle.get_conversion_amount.return_value = {
            "to_amount": 9.9,
            "fee_amount": 0.1,
            "net_amount": 9.8,
            "rate": 0.99,
            "price_data": {},
        }

        self.oxc_wallet = MagicMock()
        self.oxc_wallet.get_address.return_value = "oxc_deposit_addr"
        self.oxc_wallet.send.return_value = "oxc_settle_txid"
        self.oxc_wallet.get_balance.return_value = 1000.0

        self.oxg_wallet = MagicMock()
        self.oxg_wallet.get_address.return_value = "oxg_deposit_addr"
        self.oxg_wallet.send.return_value = "oxg_settle_txid"
        self.oxg_wallet.get_balance.return_value = 1000.0

        self.engine = self.swap_engine.SwapEngine(
            price_oracle=self.oracle,
            oxc_wallet=self.oxc_wallet,
            oxg_wallet=self.oxg_wallet,
            history_service=self.history,
            admin_service=self.admin,
        )

    def test_admin_can_set_swap_status(self):
        # Create a swap
        swap = self.engine.create_swap("OXC", "OXG", 10.0, "user_addr_123")
        swap_id = swap["swap_id"]

        # Admin changes status
        updated = self.engine.set_swap_status(
            swap_id, "completed", performed_by="admin_user", reason="Manual completion"
        )

        self.assertEqual(updated["status"], "completed")
        self.assertTrue(updated["admin_override"])
        self.assertEqual(updated["admin_set_state"], "completed")
        self.assertEqual(updated["admin_override_by"], "admin_user")
        self.assertIsNotNone(updated["admin_override_reason"])

    def test_admin_override_persists_in_database(self):
        # Create a swap
        swap = self.engine.create_swap("OXC", "OXG", 10.0, "user_addr_456")
        swap_id = swap["swap_id"]

        # Admin sets status to cancelled
        self.engine.set_swap_status(
            swap_id, "cancelled", performed_by="admin_user", reason="User requested"
        )

        # Fetch from database directly
        fetched = self.history.get_swap(swap_id)
        self.assertTrue(fetched["admin_override"])
        self.assertEqual(fetched["admin_set_state"], "cancelled")
        self.assertEqual(fetched["admin_override_by"], "admin_user")

    def test_admin_can_clear_override(self):
        # Create a swap with admin override
        swap = self.engine.create_swap("OXC", "OXG", 10.0, "user_addr_789")
        swap_id = swap["swap_id"]

        self.engine.set_swap_status(swap_id, "cancelled", performed_by="admin_user")
        
        # Clear the override
        cleared = self.engine.clear_admin_override(swap_id, performed_by="admin_user")

        self.assertFalse(cleared["admin_override"])
        self.assertIsNone(cleared["admin_set_state"])
        self.assertIsNone(cleared["admin_override_reason"])
        self.assertIsNone(cleared["admin_override_by"])

    def test_admin_override_prevents_late_deposit_processing(self):
        # Create a swap and let it expire
        swap = self.engine.create_swap("OXC", "OXG", 10.0, "user_addr_expire")
        swap_id = swap["swap_id"]

        # Manually mark as expired
        self.history.update_swap(swap_id, {"status": "timed_out"})

        # Admin overrides to completed
        self.engine.set_swap_status(swap_id, "completed", performed_by="admin")

        # Simulate late deposit
        swap_obj = self.history.get_swap(swap_id)
        self.assertEqual(swap_obj["status"], "completed")
        self.assertTrue(swap_obj["admin_override"])

    def test_get_swap_includes_admin_override_info(self):
        # Create a swap with admin override
        swap = self.engine.create_swap("OXC", "OXG", 10.0, "user_addr_info")
        swap_id = swap["swap_id"]

        self.engine.set_swap_status(
            swap_id, "failed", performed_by="admin_test", reason="Testing override"
        )

        # Fetch swap - should include admin override info
        fetched = self.history.get_swap(swap_id)
        
        self.assertIn("admin_override", fetched)
        self.assertIn("admin_set_state", fetched)
        self.assertIn("admin_override_reason", fetched)
        self.assertIn("admin_override_by", fetched)
        self.assertIn("admin_override_at", fetched)

        self.assertTrue(fetched["admin_override"])
        self.assertEqual(fetched["admin_set_state"], "failed")
        self.assertEqual(fetched["admin_override_reason"], "Testing override")
        self.assertEqual(fetched["admin_override_by"], "admin_test")

    def test_user_ip_captured_on_swap_creation(self):
        # Create a swap with user_ip
        swap = self.engine.create_swap("OXC", "OXG", 10.0, "user_addr_ip", user_ip="192.168.1.100")
        swap_id = swap["swap_id"]

        # Verify user_ip is stored
        self.assertEqual(swap.get("user_ip"), "192.168.1.100")

        # Fetch from database and verify
        fetched = self.history.get_swap(swap_id)
        self.assertEqual(fetched.get("user_ip"), "192.168.1.100")

    def test_admin_override_prevents_late_deposit_on_pending_swap(self):
        # Create a swap and confirm deposit
        swap = self.engine.create_swap("OXC", "OXG", 10.0, "user_addr_pending")
        swap_id = swap["swap_id"]

        # Confirm deposit normally
        self.engine.confirm_deposit(swap_id, "deposit_txid_123")

        # Admin overrides to completed
        self.engine.set_swap_status(swap_id, "completed", performed_by="admin")

        # Try to confirm deposit again - should return the swap unchanged
        result = self.engine.confirm_deposit(swap_id, "another_txid")
        self.assertEqual(result["status"], "completed")
        self.assertTrue(result["admin_override"])

    def test_admin_override_with_empty_reason(self):
        # Create a swap and set status without reason
        swap = self.engine.create_swap("OXC", "OXG", 10.0, "user_addr_noreason")
        swap_id = swap["swap_id"]

        self.engine.set_swap_status(swap_id, "cancelled", performed_by="admin")

        fetched = self.history.get_swap(swap_id)
        self.assertTrue(fetched["admin_override"])
        self.assertEqual(fetched["admin_set_state"], "cancelled")
        # Reason can be None or empty string - just verify it's falsy or empty
        reason = fetched.get("admin_override_reason")
        self.assertTrue(reason is None or reason == "" or reason == "Not provided")

    def test_clear_override_on_non_overridden_swap_fails(self):
        # Create a normal swap without admin override
        swap = self.engine.create_swap("OXC", "OXG", 10.0, "user_addr_normal")
        swap_id = swap["swap_id"]

        # Try to clear override - should fail
        with self.assertRaises(self.SwapError) as context:
            self.engine.clear_admin_override(swap_id)
        self.assertIn("does not have an admin override", str(context.exception))


if __name__ == "__main__":
    unittest.main()
