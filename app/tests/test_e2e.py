import os
import sys
import unittest
import tempfile
import importlib
import sqlite3
from datetime import datetime, timezone

# Add swap-service to path
_swap_service_path = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "swap-service"
)
if _swap_service_path not in sys.path:
    sys.path.insert(0, _swap_service_path)

from test_helpers import setup_test_db


class FakeOracle:
    def get_conversion_amount(
        self,
        from_coin,
        to_coin,
        amount,
        fee_percent,
        min_fee_oxc: float = 1.0,
        min_fee_oxg: float = 1.0,
    ):
        rate = 2.0 if from_coin == "OXC" else 0.5
        to_amount = amount * rate
        fee = to_amount * (fee_percent / 100)

        min_fee = min_fee_oxg if to_coin == "OXG" else min_fee_oxc
        if fee < min_fee:
            fee = min_fee

        net_amount = to_amount - fee
        return {
            "from_coin": from_coin,
            "to_coin": to_coin,
            "from_amount": amount,
            "to_amount": to_amount,
            "fee_amount": fee,
            "net_amount": net_amount,
            "rate": rate,
            "price_data": {
                "price": rate,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        }

    def get_price(self, _from_coin, _to_coin):
        return {
            "price": 1.0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "oxc_usdt": 0.2,
            "oxg_usdt": 0.1,
            "source": "test",
        }


class FakeWallet:
    def __init__(self, coin, send_error: Exception = None):
        self.coin = coin
        self.send_error = send_error

    def get_address(self):
        return f"{self.coin.lower()}_addr"

    def get_labeled_address(self, label):
        return f"{self.coin.lower()}_{label}_addr"

    def send(self, _address, _amount):
        if self.send_error:
            raise self.send_error
        return f"tx_{self.coin.lower()}"

    def get_balance(self):
        return 100.0

    def get_transaction(self, _txid):
        return {"confirmations": 0}


class TestE2EApiFlow(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["DB_PATH"] = os.path.join(self._tmpdir.name, "test.db")
        os.environ["TESTING_MODE"] = "false"
        os.environ["SWAP_CONFIRMATIONS_REQUIRED"] = "0"

        setup_test_db(os.environ["DB_PATH"])

        for mod in [
            "config",
            "db_pool",
            "migrations",
            "api",
            "swap_engine",
            "swap_history",
            "price_history",
            "admin_service",
            "utils",
            "logger",
        ]:
            if mod in sys.modules:
                del sys.modules[mod]
        
        # Also clear any submodules of swap-service if they were loaded with different names
        for mod_name in list(sys.modules.keys()):
            if mod_name.startswith(("db_pool", "admin_service", "swap_history", "migrations", "config", "utils", "structured_logging", "logger", "api", "swap_engine")):
                del sys.modules[mod_name]

        api = importlib.import_module("api")
        swap_engine = importlib.import_module("swap_engine")
        swap_history = importlib.import_module("swap_history")
        price_history = importlib.import_module("price_history")
        admin_service = importlib.import_module("admin_service")

        self.db_path = os.environ["DB_PATH"]
        self.oracle = FakeOracle()
        self.oxc_wallet = FakeWallet("OXC")
        self.oxg_wallet = FakeWallet("OXG")

        self.history_service = swap_history.SwapHistoryService()
        self.price_history = price_history.PriceHistoryService(self.oracle)
        self.admin_service = admin_service.AdminService(db_path=self.db_path)
        self.admin_service.create_admin("swap", "changeme26")

        self.engine = swap_engine.SwapEngine(
            price_oracle=self.oracle,
            oxc_wallet=self.oxc_wallet,
            oxg_wallet=self.oxg_wallet,
            history_service=self.history_service,
            fee_percent=1.0,
        )

        api.init_app(
            self.engine,
            self.oracle,
            self.price_history,
            self.history_service,
            self.admin_service,
        )
        self.client = api.app.test_client()

    def _create_and_confirm_swap(self, from_coin, to_coin, amount):
        quote = self.client.post(
            "/api/v1/quote",
            json={"from": from_coin, "to": to_coin, "amount": amount},
        )
        self.assertEqual(quote.status_code, 200)

        resp = self.client.post(
            "/api/v1/swap",
            json={
                "from": from_coin,
                "to": to_coin,
                "amount": amount,
                "user_address": "user_addr_123",
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        swap_id = data["data"]["swap_id"]

        confirm = self.client.post(
            f"/api/v1/swap/{swap_id}/confirm",
            json={"deposit_txid": "test_txid"},
        )
        self.assertEqual(confirm.status_code, 200)
        return swap_id

    def test_swaps_recorded_in_db_for_both_pairs(self):
        self._create_and_confirm_swap("OXC", "OXG", 10)
        self._create_and_confirm_swap("OXG", "OXC", 5)

        swaps_resp = self.client.get("/api/v1/swaps")
        swaps_data = swaps_resp.get_json()["data"]["swaps"]
        self.assertEqual(len(swaps_data), 2)

        with sqlite3.connect(self.db_path) as conn:
            count = conn.execute("SELECT COUNT(*) FROM swaps").fetchone()[0]
            completed = conn.execute(
                "SELECT COUNT(*) FROM swaps WHERE status = ?",
                ("completed",),
            ).fetchone()[0]
        self.assertEqual(count, 2)
        self.assertEqual(completed, 2)

    def test_delayed_swap_and_queue_processing(self):
        from wallet_rpc import WalletRPCError

        self.oxg_wallet.send_error = WalletRPCError("insufficient funds")
        resp = self.client.post(
            "/api/v1/swap",
            json={
                "from": "OXC",
                "to": "OXG",
                "amount": 10,
                "user_address": "user_addr_123",
            },
        )
        swap_id = resp.get_json()["data"]["swap_id"]

        confirm = self.client.post(
            f"/api/v1/swap/{swap_id}/confirm",
            json={"deposit_txid": "test_txid"},
        )
        self.assertEqual(confirm.status_code, 200)
        data = confirm.get_json()["data"]
        self.assertEqual(data["status"], "delayed")

        blocked_quote = self.client.post(
            "/api/v1/quote",
            json={"from": "OXC", "to": "OXG", "amount": 12},
        ).get_json()["data"]
        self.assertTrue(blocked_quote["liquidity_blocked"])

        blocked_swap = self.client.post(
            "/api/v1/swap",
            json={
                "from": "OXC",
                "to": "OXG",
                "amount": 12,
                "user_address": "user_addr_123",
            },
        )
        self.assertEqual(blocked_swap.status_code, 503)
        self.assertEqual(blocked_swap.get_json().get("error_code"), "LIQUIDITY_DELAY")

        self.oxg_wallet.send_error = None
        processed = self.engine.process_delayed_swaps()
        self.assertEqual(processed, 1)

        swap = self.client.get(f"/api/v1/swap/{swap_id}").get_json()["data"]
        self.assertEqual(swap["status"], "completed")

    def test_cancel_swap_without_deposit(self):
        resp = self.client.post(
            "/api/v1/swap",
            json={
                "from": "OXG",
                "to": "OXC",
                "amount": 5,
                "user_address": "user_addr_123",
            },
        )
        self.assertEqual(resp.status_code, 200)
        swap_id = resp.get_json()["data"]["swap_id"]

        cancel = self.client.post(f"/api/v1/swap/{swap_id}/cancel")
        self.assertEqual(cancel.status_code, 200)
        self.assertEqual(cancel.get_json()["data"]["status"], "cancelled")

    def test_admin_dashboard_basic_auth(self):
        import base64

        token = base64.b64encode(b"swap:changeme26").decode("utf-8")
        resp = self.client.get(
            "/api/v1/admin/dashboard",
            headers={"Authorization": f"Basic {token}"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()["data"]
        self.assertIn("wallets", data)
        self.assertIn("stats", data)

    def test_invalid_quote_and_swap_inputs(self):
        bad_quote = self.client.post(
            "/api/v1/quote",
            json={"from": "OXC", "to": "OXG"},
        )
        self.assertEqual(bad_quote.status_code, 400)

        bad_amount = self.client.post(
            "/api/v1/quote",
            json={"from": "OXC", "to": "OXG", "amount": "not_a_number"},
        )
        self.assertEqual(bad_amount.status_code, 400)

        bad_swap = self.client.post(
            "/api/v1/swap",
            json={"from": "OXC", "to": "OXG", "amount": 10},
        )
        self.assertEqual(bad_swap.status_code, 400)

        bad_coin = self.client.post(
            "/api/v1/swap",
            json={
                "from": "OXC",
                "to": "BAD",
                "amount": 10,
                "user_address": "user_addr_123",
            },
        )
        self.assertEqual(bad_coin.status_code, 400)

    def test_fuzz_swap_inputs(self):
        candidates = [
            {"from": "OXC", "to": "OXG", "amount": -1, "user_address": "user_addr_123"},
            {"from": "OXC", "to": "OXG", "amount": 0, "user_address": "user_addr_123"},
            {
                "from": "OXC",
                "to": "OXG",
                "amount": 999999999,
                "user_address": "user_addr_123",
            },
            {
                "from": "OXC",
                "to": "OXG",
                "amount": "nan",
                "user_address": "user_addr_123",
            },
            {"from": "OXC", "to": "OXG", "amount": 10, "user_address": ""},
            {"from": "OXC", "to": "OXG", "amount": 10, "user_address": "bad!"},
        ]

        for payload in candidates:
            resp = self.client.post("/api/v1/swap", json=payload)
            self.assertNotEqual(resp.status_code, 200, payload)

    def test_admin_routes_require_authentication(self):
        import base64

        admin_endpoints = [
            ("/api/v1/admin/dashboard", "GET"),
            ("/api/v1/admin/settings", "GET"),
            ("/api/v1/admin/settings", "POST"),
            ("/api/v1/admin/swaps-enabled", "GET"),
            ("/api/v1/admin/swaps-enabled", "POST"),
            ("/api/v1/admin/fee", "GET"),
            ("/api/v1/admin/fee", "POST"),
        ]

        for endpoint, method in admin_endpoints:
            if method == "GET":
                resp = self.client.get(endpoint)
            else:
                resp = self.client.post(endpoint, json={})
            self.assertEqual(
                resp.status_code, 401, f"{method} {endpoint} should require auth"
            )

        token = base64.b64encode(b"swap:changeme26").decode("utf-8")
        auth_header = {"Authorization": f"Basic {token}"}

        for endpoint, method in admin_endpoints:
            if method == "GET":
                resp = self.client.get(endpoint, headers=auth_header)
            else:
                resp = self.client.post(endpoint, json={}, headers=auth_header)
            self.assertNotEqual(
                resp.status_code, 401, f"{method} {endpoint} should work with auth"
            )

    def test_status_endpoint_contains_swap_settings(self):
        resp = self.client.get("/api/v1/status")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()["data"]

        self.assertIn("fee_percent", data)
        self.assertIn("min_fee_oxc", data)
        self.assertIn("min_fee_oxg", data)
        self.assertIn("min_amount", data)
        self.assertIn("max_amount", data)
        self.assertIn("confirmations_required", data)
        self.assertIn("swaps_enabled", data)


if __name__ == "__main__":
    unittest.main()
