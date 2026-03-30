import os
import sys
import unittest

_swap_service_path = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "swap-service"
)
if _swap_service_path not in sys.path:
    sys.path.insert(0, _swap_service_path)


class TestSwapControlAPI(unittest.TestCase):
    def setUp(self):
        import tempfile

        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["DB_PATH"] = os.path.join(self._tmpdir.name, "test.db")

        import importlib

        for mod in ("config", "admin_service"):
            if mod in sys.modules:
                del sys.modules[mod]

        admin_service = importlib.import_module("admin_service")
        self.AdminService = admin_service.AdminService

    def test_get_swaps_enabled_requires_auth(self):
        import requests
        import os

        DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "ordex.db")
        if not os.path.exists(DB_PATH):
            self.skipTest(f"Database not found at {DB_PATH}")

        response = requests.get("http://localhost:8080/api/v1/admin/swaps-enabled")
        self.assertEqual(response.status_code, 401)

    def test_set_swaps_enabled_requires_auth(self):
        import requests
        import os

        DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "ordex.db")
        if not os.path.exists(DB_PATH):
            self.skipTest(f"Database not found at {DB_PATH}")

        response = requests.post(
            "http://localhost:8080/api/v1/admin/swaps-enabled", json={"enabled": False}
        )
        self.assertEqual(response.status_code, 401)

    def test_status_endpoint_public(self):
        import requests
        import os

        DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "ordex.db")
        if not os.path.exists(DB_PATH):
            self.skipTest(f"Database not found at {DB_PATH}")

        response = requests.get("http://localhost:8080/api/v1/status")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("swaps_enabled", data["data"])
