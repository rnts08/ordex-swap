import os
import sys
import unittest
import tempfile
import importlib
import base64
from datetime import datetime, timezone

# Add swap-service to path
_swap_service_path = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "swap-service"
)
if _swap_service_path not in sys.path:
    sys.path.insert(0, _swap_service_path)

class TestSwapControlAPI(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["DB_PATH"] = os.path.join(self._tmpdir.name, "test.db")
        os.environ["TESTING_MODE"] = "true"

        for mod in ("config", "api", "swap_engine", "admin_service"):
            if mod in sys.modules:
                del sys.modules[mod]

        api = importlib.import_module("api")
        swap_engine = importlib.import_module("swap_engine")
        admin_service = importlib.import_module("admin_service")
        
        # Mock dependencies
        oracle = importlib.import_module("price_oracle").PriceOracle()
        history = importlib.import_module("swap_history").SwapHistoryService()
        price_history = importlib.import_module("price_history").PriceHistoryService(oracle)
        self.admin_service = admin_service.AdminService(db_path=os.environ["DB_PATH"])
        self.admin_service.create_admin("admin", "adminpass")
        
        oxc_wallet = importlib.import_module("unittest.mock").MagicMock()
        oxg_wallet = importlib.import_module("unittest.mock").MagicMock()

        self.engine = swap_engine.SwapEngine(
            price_oracle=oracle,
            oxc_wallet=oxc_wallet,
            oxg_wallet=oxg_wallet,
            history_service=history,
        )

        api.init_app(self.engine, oracle, price_history, history, self.admin_service)
        self.client = api.app.test_client()
        
        self.auth_header = {
            "Authorization": f"Basic {base64.b64encode(b'admin:adminpass').decode()}"
        }

    def test_get_swaps_enabled_requires_auth(self):
        response = self.client.get("/api/v1/admin/swaps-enabled")
        self.assertEqual(response.status_code, 401)

    def test_set_swaps_enabled_requires_auth(self):
        response = self.client.post(
            "/api/v1/admin/swaps-enabled", json={"enabled": False}
        )
        self.assertEqual(response.status_code, 401)

    def test_status_endpoint_public(self):
        response = self.client.get("/api/v1/status")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("swaps_enabled", data["data"])

if __name__ == "__main__":
    unittest.main()
