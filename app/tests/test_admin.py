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
