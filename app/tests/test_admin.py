import os
import sys
import unittest
import tempfile
import importlib

# Add swap-service to path BEFORE any imports
_swap_service_path = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "swap-service"
)
if _swap_service_path not in sys.path:
    sys.path.insert(0, _swap_service_path)


class TestAdminService(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["DB_PATH"] = os.path.join(self._tmpdir.name, "test.db")

        for mod in ("config", "admin_service"):
            if mod in sys.modules:
                del sys.modules[mod]

        admin_service = importlib.import_module("admin_service")
        self.AdminService = admin_service.AdminService

    def test_default_admin_created_and_authenticates(self):
        service = self.AdminService()
        self.assertTrue(service.verify_credentials("swap", "changeme26"))
        self.assertFalse(service.verify_credentials("swap", "wrongpass"))

    def test_wallet_address_persistence_and_rotate(self):
        service = self.AdminService()
        generator_calls = {"count": 0}

        def generator():
            generator_calls["count"] += 1
            return f"addr_{generator_calls['count']}"

        first = service.get_or_create_wallet_address("OXC", "liquidity", generator)
        second = service.get_or_create_wallet_address("OXC", "liquidity", generator)
        self.assertEqual(first, second)
        self.assertEqual(generator_calls["count"], 1)

        rotated = service.rotate_wallet_address("OXC", "liquidity", generator)
        self.assertNotEqual(rotated, first)

    def test_create_additional_admin(self):
        service = self.AdminService()
        created = service.create_admin("alice", "secretpass")
        self.assertTrue(created)
        self.assertTrue(service.verify_credentials("alice", "secretpass"))

    def test_swaps_enabled_default(self):
        service = self.AdminService()
        self.assertTrue(service.get_swaps_enabled())

    def test_swaps_enabled_set_and_get(self):
        service = self.AdminService()
        self.assertTrue(service.get_swaps_enabled())

        result = service.set_swaps_enabled(False)
        self.assertTrue(result)
        self.assertFalse(service.get_swaps_enabled())

        result = service.set_swaps_enabled(True)
        self.assertTrue(result)
        self.assertTrue(service.get_swaps_enabled())

    def test_wallet_actions_log_and_retrieve(self):
        service = self.TestAdminService()
        self.assertTrue(
            service.log_wallet_action(
                action_type="withdraw",
                coin="OXC",
                purpose="liquidity",
                amount=1.5,
                address="testaddr123",
                txid="tx123",
                performed_by="admin",
            )
        )

        actions = service.get_wallet_actions(limit=10)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["action_type"], "withdraw")
        self.assertEqual(actions[0]["coin"], "OXC")
        self.assertEqual(actions[0]["amount"], 1.5)
        self.assertEqual(actions[0]["address"], "testaddr123")
        self.assertEqual(actions[0]["txid"], "tx123")
        self.assertEqual(actions[0]["performed_by"], "admin")

    def test_wallet_actions_empty(self):
        service = self.AdminService()
        actions = service.get_wallet_actions(limit=10)
        self.assertEqual(len(actions), 0)
