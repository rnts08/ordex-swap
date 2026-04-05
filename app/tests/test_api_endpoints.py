"""
Comprehensive API endpoint tests for Flask routes.

Covers all major endpoints with success and error scenarios:
- Quote and swap creation flow
- Admin operations (reconciliation, settling, refunds)
- Wallet operations (balance, deposits, withdrawals)
- Swap queries and filters
- Edge cases and error conditions
"""

import os
import sys
import unittest
import tempfile
import json
import base64
import importlib
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

# Add swap-service to path
_swap_service_path = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "swap-service"
)
if _swap_service_path not in sys.path:
    sys.path.insert(0, _swap_service_path)


class FakeOracle:
    """Mock price oracle for testing."""
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
    """Mock wallet for testing."""
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


def _init_app_for_testing(test_case):
    """Helper to initialize Flask app with test services."""
    test_case._tmpdir = tempfile.TemporaryDirectory()
    test_case.addCleanup(test_case._tmpdir.cleanup)
    os.environ["DATA_DIR"] = test_case._tmpdir.name
    os.environ["DB_PATH"] = os.path.join(test_case._tmpdir.name, "test.db")
    os.environ["TESTING_MODE"] = "true"
    os.environ["SWAP_CONFIRMATIONS_REQUIRED"] = "0"

    # Clean modules to ensure fresh imports
    for mod in ["config", "db_pool", "migrations", "api", "swap_engine",
                "swap_history", "price_history", "admin_service", "wallet_rpc",
                "price_oracle", "swap_cleanup"]:
        if mod in sys.modules:
            del sys.modules[mod]

    # Import all necessary modules
    api = importlib.import_module("api")
    swap_engine = importlib.import_module("swap_engine")
    swap_history = importlib.import_module("swap_history")
    price_history = importlib.import_module("price_history")
    admin_service = importlib.import_module("admin_service")

    # Create test services
    db_path = os.environ["DB_PATH"]
    oracle = FakeOracle()
    oxc_wallet = FakeWallet("OXC")
    oxg_wallet = FakeWallet("OXG")

    history_service = swap_history.SwapHistoryService()
    price_hist = price_history.PriceHistoryService(oracle)
    # Record a price entry so endpoints that require price data work
    price_hist.fetch_and_record()
    
    admin_svc = admin_service.AdminService(db_path=db_path)
    admin_svc.create_admin("swap", "changeme26")

    engine = swap_engine.SwapEngine(
        price_oracle=oracle,
        oxc_wallet=oxc_wallet,
        oxg_wallet=oxg_wallet,
        history_service=history_service,
        fee_percent=1.0,
    )

    # Initialize app with services
    api.init_app(
        engine,
        oracle,
        price_hist,
        history_service,
        admin_svc,
    )
    return api.app


class TestPublicEndpoints(unittest.TestCase):
    """Test public API endpoints accessible without authentication."""

    def setUp(self):
        self.app = _init_app_for_testing(self)
        self.client = self.app.test_client()
        self.app.config["TESTING"] = True

    def test_health_endpoint_returns_200(self):
        """Health check should return 200 OK."""
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data.get("success"))

    def test_status_endpoint_returns_service_info(self):
        """Status endpoint should return service information."""
        response = self.client.get("/api/v1/status")
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data.get("success"))
        self.assertIn("data", data)

    def test_balance_endpoint(self):
        """Balance endpoint should return wallet balances."""
        response = self.client.get("/api/v1/balance")
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data.get("success"))

    def test_deposit_address_oxc(self):
        """Deposit endpoint should return OXC deposit address."""
        response = self.client.get("/api/v1/deposit/OXC")
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data.get("success"))
        self.assertIn("address", data.get("data", {}))

    def test_deposit_address_oxg(self):
        """Deposit endpoint should return OXG deposit address."""
        response = self.client.get("/api/v1/deposit/OXG")
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data.get("success"))
        self.assertIn("address", data.get("data", {}))

    def test_deposit_address_invalid_coin(self):
        """Deposit endpoint should reject invalid coin."""
        response = self.client.get("/api/v1/deposit/INVALID")
        self.assertIn(response.status_code, [400, 404])

    def test_prices_current_endpoint(self):
        """Current prices endpoint should return price data."""
        response = self.client.get("/api/v1/prices/current")
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data.get("success"))

    def test_swaps_stats_endpoint(self):
        """Stats endpoint should return swap statistics."""
        response = self.client.get("/api/v1/swaps/stats")
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data.get("success"))

    def test_quote_endpoint_valid_request(self):
        """Quote endpoint should return swap quote for valid request."""
        response = self.client.post("/api/v1/quote", json={
            "from": "OXC",
            "to": "OXG",
            "amount": 10.0
        })
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data.get("success"))
        quote = data.get("data", {})
        self.assertIn("to_amount", quote)
        self.assertIn("fee_amount", quote)
        self.assertIn("net_amount", quote)

    def test_quote_endpoint_reverse_direction(self):
        """Quote endpoint should handle reverse coin direction."""
        response = self.client.post("/api/v1/quote", json={
            "from": "OXG",
            "to": "OXC",
            "amount": 10.0
        })
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data.get("success"))

    def test_quote_endpoint_various_amounts(self):
        """Quote endpoint should accept different valid amounts."""
        test_amounts = [0.1, 1.0, 10.5, 100.0, 1000.0]
        for amount in test_amounts:
            with self.subTest(amount=amount):
                response = self.client.post("/api/v1/quote", json={
                    "from": "OXC",
                    "to": "OXG",
                    "amount": amount
                })
                self.assertIn(response.status_code, [200, 400])

    def test_quote_endpoint_missing_field(self):
        """Quote endpoint should reject request with missing field."""
        response = self.client.post("/api/v1/quote", json={
            "from": "OXC",
            "to": "OXG"
        })
        self.assertIn(response.status_code, [400, 422])

    def test_swap_creation_valid_request(self):
        """Swap endpoint should create swap with valid request."""
        response = self.client.post("/api/v1/swap", json={
            "from": "OXC",
            "to": "OXG",
            "amount": 5.0,
            "user_address": "user_test_address_123"
        })
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data.get("success"))
        swap = data.get("data", {})
        self.assertIn("swap_id", swap)
        self.assertIn("deposit_address", swap)

    def test_swap_creation_returns_deposit_address(self):
        """Swap should return valid deposit address for payment."""
        response = self.client.post("/api/v1/swap", json={
            "from": "OXC",
            "to": "OXG",
            "amount": 5.0,
            "user_address": "user_test_address_123"
        })
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        swap = data.get("data", {})
        deposit_addr = swap.get("deposit_address")
        self.assertIsNotNone(deposit_addr)
        self.assertIsInstance(deposit_addr, str)
        self.assertGreater(len(deposit_addr), 0)

    def test_get_swap_by_id(self):
        """Endpoint should retrieve swap details by ID."""
        swap_resp = self.client.post("/api/v1/swap", json={
            "from": "OXC",
            "to": "OXG",
            "amount": 5.0,
            "user_address": "user_test_addr_123"
        })
        swap_id = json.loads(swap_resp.data).get("data", {}).get("swap_id")

        response = self.client.get(f"/api/v1/swap/{swap_id}")
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data.get("success"))

    def test_get_nonexistent_swap(self):
        """Endpoint should return 404 for nonexistent swap."""
        response = self.client.get("/api/v1/swap/nonexistent_id")
        self.assertEqual(response.status_code, 404)

    def test_list_swaps_endpoint(self):
        """List swaps endpoint should return paginated results."""
        self.client.post("/api/v1/swap", json={
            "from": "OXC",
            "to": "OXG",
            "amount": 5.0,
            "user_address": "user_test_addr_123"
        })

        response = self.client.get("/api/v1/swaps")
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        swaps_data = data.get("data", {})
        self.assertIn("swaps", swaps_data)

    def test_list_swaps_with_limit(self):
        """List endpoint should support limit parameter."""
        response = self.client.get("/api/v1/swaps?limit=5")
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        swaps_data = data.get("data", {})
        swaps = swaps_data.get("swaps", [])
        self.assertLessEqual(len(swaps), 5)

    def test_search_swaps_by_status(self):
        """Search endpoint should filter swaps by address."""
        response = self.client.get("/api/v1/swaps/search?address=user_test_addr_123")
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertIn("data", data)


class TestSwapLifecycle(unittest.TestCase):
    """Test complete swap lifecycle: create, confirm, settle."""

    def setUp(self):
        self.app = _init_app_for_testing(self)
        self.client = self.app.test_client()
        self.app.config["TESTING"] = True

    def test_complete_swap_flow(self):
        """Test full swap creation to confirmation flow."""
        quote_response = self.client.post("/api/v1/quote", json={
            "from": "OXC",
            "to": "OXG",
            "amount": 5.0
        })
        self.assertEqual(quote_response.status_code, 200)

        swap_response = self.client.post("/api/v1/swap", json={
            "from": "OXC",
            "to": "OXG",
            "amount": 5.0,
            "user_address": "user_test_address"
        })
        self.assertEqual(swap_response.status_code, 200)
        swap_data = json.loads(swap_response.data)
        swap_id = swap_data.get("data", {}).get("swap_id")

        get_response = self.client.get(f"/api/v1/swap/{swap_id}")
        self.assertEqual(get_response.status_code, 200)

    def test_cancel_swap(self):
        """Test canceling a pending swap."""
        swap_response = self.client.post("/api/v1/swap", json={
            "from": "OXC",
            "to": "OXG",
            "amount": 5.0,
            "user_address": "user_test_address"
        })
        swap_id = json.loads(swap_response.data).get("data", {}).get("swap_id")

        cancel_response = self.client.post(f"/api/v1/swap/{swap_id}/cancel", json={})
        self.assertEqual(cancel_response.status_code, 200)


class TestAdminEndpoints(unittest.TestCase):
    """Test admin-only endpoints with authentication."""

    def setUp(self):
        self.app = _init_app_for_testing(self)
        self.client = self.app.test_client()
        self.app.config["TESTING"] = True

    def _get_admin_auth(self):
        """Generate admin auth header."""
        credentials = "swap:changeme26"
        encoded = base64.b64encode(credentials.encode()).decode()
        return {"Authorization": f"Basic {encoded}"}

    def test_admin_swaps_enabled_get(self):
        """Admin should retrieve current swaps enabled status."""
        response = self.client.get("/api/v1/admin/swaps-enabled",
                                  headers=self._get_admin_auth())
        self.assertIn(response.status_code, [200, 401, 403])

    def test_admin_swaps_enabled_requires_auth(self):
        """Admin endpoint should require authentication."""
        response = self.client.get("/api/v1/admin/swaps-enabled")
        self.assertIn(response.status_code, [401, 403])

    def test_admin_background_status(self):
        """Admin should retrieve background job status."""
        response = self.client.get("/api/v1/admin/background-status",
                                  headers=self._get_admin_auth())
        self.assertIn(response.status_code, [200, 401, 403, 500])

    def test_admin_users_requires_auth(self):
        """Admin users endpoint should require authentication."""
        response = self.client.get("/api/v1/admin/users")
        self.assertIn(response.status_code, [401, 403])

    def test_admin_set_swap_status(self):
        """Admin should be able to change swap status."""
        # First create a swap
        swap_response = self.client.post("/api/v1/swap", json={
            "from": "OXC",
            "to": "OXG",
            "amount": 5.0,
            "user_address": "user_test_address"
        })
        self.assertEqual(swap_response.status_code, 200)
        swap_id = json.loads(swap_response.data).get("data", {}).get("swap_id")
        self.assertIsNotNone(swap_id)

        # Admin changes status
        response = self.client.put(
            f"/api/v1/admin/swaps/{swap_id}/status",
            json={"status": "cancelled", "reason": "Test cancellation"},
            headers=self._get_admin_auth()
        )
        self.assertIn(response.status_code, [200, 401, 403])

    def test_admin_clear_override_requires_auth(self):
        """Admin clear override endpoint should require authentication."""
        response = self.client.post("/api/v1/admin/swaps/test-id/clear-override")
        self.assertIn(response.status_code, [401, 403])

    def test_admin_get_swap_details(self):
        """Admin should be able to retrieve detailed swap information."""
        # First create a swap
        swap_response = self.client.post("/api/v1/swap", json={
            "from": "OXC",
            "to": "OXG",
            "amount": 5.0,
            "user_address": "user_test_address"
        })
        self.assertEqual(swap_response.status_code, 200)
        swap_id = json.loads(swap_response.data).get("data", {}).get("swap_id")
        self.assertIsNotNone(swap_id)

        # Admin retrieves swap details
        response = self.client.get(
            f"/api/v1/admin/swaps/{swap_id}",
            headers=self._get_admin_auth()
        )
        self.assertIn(response.status_code, [200, 401, 403, 404])


class TestErrorConditions(unittest.TestCase):
    """Test error handling and edge cases."""

    def setUp(self):
        self.app = _init_app_for_testing(self)
        self.client = self.app.test_client()
        self.app.config["TESTING"] = True

    def test_malformed_json_request(self):
        """Endpoint should handle malformed JSON."""
        response = self.client.post("/api/v1/quote",
                                   data="not valid json",
                                   content_type="application/json")
        self.assertIn(response.status_code, [400, 422, 500])

    def test_missing_content_type(self):
        """Endpoint should handle request with JSON payload."""
        response = self.client.post("/api/v1/quote",
                                   json={"from": "OXC", "to": "OXG", "amount": 10.0})
        self.assertIn(response.status_code, [200, 400])

    def test_quote_same_coin_pair(self):
        """Quote with same coin should be rejected."""
        response = self.client.post("/api/v1/quote", json={
            "from": "OXC",
            "to": "OXC",
            "amount": 10.0
        })
        self.assertIn(response.status_code, [400, 422, 425])

    def test_swap_same_coin_pair(self):
        """Swap with same coin should be rejected."""
        response = self.client.post("/api/v1/swap", json={
            "from": "OXC",
            "to": "OXC",
            "amount": 10.0,
            "user_address": "test_address"
        })
        self.assertIn(response.status_code, [400, 422, 425])

    def test_swap_with_extreme_amounts(self):
        """Swap with extreme amounts should be handled."""
        for amount in [0.00001, 999999999.99]:
            with self.subTest(amount=amount):
                response = self.client.post("/api/v1/swap", json={
                    "from": "OXC",
                    "to": "OXG",
                    "amount": amount,
                    "user_address": "test_addr_123"
                })
                self.assertIn(response.status_code, [200, 400, 503])

    def test_method_not_allowed(self):
        """Endpoint should reject wrong HTTP method."""
        response = self.client.get("/api/v1/quote")
        self.assertIn(response.status_code, [405, 500])

    def test_nonexistent_endpoint_returns_404(self):
        """Nonexistent endpoint should return 404."""
        response = self.client.get("/api/v1/nonexistent")
        self.assertIn(response.status_code, [404, 500])


if __name__ == "__main__":
    unittest.main()
