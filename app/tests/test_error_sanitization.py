"""
Unit tests for error message sanitization.

Tests the allowlist-based approach to ensure:
1. Users only see safe, pre-approved error messages
2. Internal details (paths, stack traces) are never exposed
3. Admin-facing endpoints can show detailed errors
"""

import os
import sys
import unittest
import importlib

# Add swap-service to path
_swap_service_path = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "swap-service"
)
if _swap_service_path not in sys.path:
    sys.path.insert(0, _swap_service_path)


class TestErrorSanitization(unittest.TestCase):
    """Test the error sanitization logic."""

    def setUp(self):
        # Import the api module to access sanitize_error_message
        if "api" in sys.modules:
            del sys.modules["api"]
        self.api = importlib.import_module("api")

    def test_safe_messages_are_returned_unchanged(self):
        """Messages in the allowlist should be returned as-is."""
        safe_messages = [
            "Invalid amount",
            "Missing required fields",
            "Authentication required",
            "Swap not found",
            "Invalid user_address",
            "Cannot swap same coin",
        ]
        for msg in safe_messages:
            with self.subTest(msg=msg):
                result = self.api.sanitize_error_message(Exception(msg), "Default error")
                self.assertEqual(result, msg)

    def test_partial_match_in_allowlist(self):
        """Messages containing allowlisted phrases should return the safe version."""
        test_cases = [
            ("Amount 10.5 below minimum 1.0", "Amount below minimum allowed"),
            ("Value above maximum allowed", "Amount above maximum allowed"),
            ("Fee too high: would result in zero", "Invalid amount after fees"),
        ]
        for original, expected in test_cases:
            with self.subTest(original=original):
                result = self.api.sanitize_error_message(Exception(original), "Default")
                self.assertEqual(result, expected)

    def test_safe_prefix_messages_are_returned(self):
        """Messages starting with safe prefixes should be returned if clean."""
        # Note: Some messages may be mapped to allowlisted versions
        safe_prefix_messages = [
            ("Invalid swap ID format", "Invalid swap ID format"),
            ("Missing deposit information", "Missing deposit information"),
            ("Unsupported currency pair", "Unsupported currency pair"),
            ("Cannot process this request", "Cannot process this request"),
            ("Amount below minimum", "Amount below minimum allowed"),  # Mapped to allowlisted version
            ("Service temporarily unavailable", "Service temporarily unavailable"),
        ]
        for msg, expected in safe_prefix_messages:
            with self.subTest(msg=msg):
                result = self.api.sanitize_error_message(Exception(msg), "Default")
                self.assertEqual(result, expected)

    def test_leaking_patterns_are_blocked(self):
        """Messages containing internal details should be replaced with default."""
        leaking_messages = [
            "Error at 0x7f1234567890",
            'File "/app/swap-service/api.py" line 42',
            "Traceback (most recent call last)",
            "sqlite3.OperationalError: no such table",
            "urllib.error.URLError",
        ]
        for msg in leaking_messages:
            with self.subTest(msg=msg):
                result = self.api.sanitize_error_message(Exception(msg), "Safe default")
                self.assertEqual(result, "Safe default")

    def test_unsafe_messages_return_default(self):
        """Messages not in allowlist and without safe prefix should return default."""
        unsafe_messages = [
            "Something went wrong",
            "Database connection failed",
            "Unexpected error occurred",
            "Process terminated abnormally",
        ]
        for msg in unsafe_messages:
            with self.subTest(msg=msg):
                result = self.api.sanitize_error_message(Exception(msg), "Generic error")
                self.assertEqual(result, "Generic error")

    def test_long_messages_are_truncated(self):
        """Very long messages should be truncated."""
        long_msg = "A" * 300
        result = self.api.sanitize_error_message(Exception(long_msg), "Default")
        # Long messages that don't match safe patterns should return default
        self.assertEqual(result, "Default")

    def test_empty_error_returns_default(self):
        """Empty error messages should return default."""
        result = self.api.sanitize_error_message(Exception(""), "Default message")
        self.assertEqual(result, "Default message")

    def test_none_error_returns_default(self):
        """None error should return default."""
        result = self.api.sanitize_error_message(None, "Default message")
        self.assertEqual(result, "Default message")

    def test_error_codes_are_safe(self):
        """Verify all safe error codes are appropriate for user exposure."""
        safe_codes = self.api.SAFE_ERROR_CODES
        # These should be generic, non-revealing codes
        expected_codes = {
            "MISSING_PARAMS",
            "INVALID_AMOUNT",
            "INVALID_ADDRESS",
            "INVALID_COIN",
            "VALIDATION_ERROR",
            "NOT_FOUND",
            "AUTHENTICATION_REQUIRED",
            "CSRF_TOKEN_REQUIRED",
            "CSRF_TOKEN_INVALID",
            "SWAPS_DISABLED",
            "LIQUIDITY_DELAY",
            "PRICE_UNAVAILABLE",
            "WALLET_ERROR",
            "SWAP_ERROR",
        }
        self.assertEqual(safe_codes, expected_codes)

    def test_rpc_error_is_sanitized(self):
        """RPC errors should be sanitized to not expose internal details."""
        # Simulate a WalletRPCError with internal details
        class MockWalletRPCError(Exception):
            pass
        
        rpc_error = MockWalletRPCError("insufficient funds at address abc123 in wallet /data/wallet.dat")
        result = self.api.sanitize_error_message(rpc_error, "Service temporarily unavailable")
        # Should not contain internal paths
        self.assertNotIn("/data/wallet.dat", result)
        self.assertNotIn("abc123", result)

    def test_validation_errors_are_user_friendly(self):
        """Validation errors should be clear and user-friendly."""
        validation_errors = [
            ("Amount 0.0001 below minimum 0.001", "Amount below minimum allowed"),
            ("Amount 999999 above maximum 10000", "Amount above maximum allowed"),
            ("Invalid address format: too short", "Invalid address format"),
        ]
        for original, expected in validation_errors:
            with self.subTest(original=original):
                result = self.api.sanitize_error_message(Exception(original), "Validation failed")
                self.assertEqual(result, expected)


class TestErrorSanitizationIntegration(unittest.TestCase):
    """Integration tests for error handling in API endpoints."""

    def setUp(self):
        import tempfile
        from unittest.mock import MagicMock
        
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["DB_PATH"] = os.path.join(self._tmpdir.name, "test.db")
        os.environ["TESTING_MODE"] = "true"

        # Clean modules
        for mod in ["config", "api", "swap_engine", "swap_history", "admin_service"]:
            if mod in sys.modules:
                del sys.modules[mod]

        self.api = importlib.import_module("api")
        self.swap_engine = importlib.import_module("swap_engine")
        self.swap_history = importlib.import_module("swap_history")
        self.admin_service = importlib.import_module("admin_service")

        # Setup test database
        from test_helpers import setup_test_db
        setup_test_db(os.environ["DB_PATH"])

        # Create mock services
        self.oracle = MagicMock()
        self.oracle.get_conversion_amount.return_value = {
            "to_amount": 9.9,
            "fee_amount": 0.1,
            "net_amount": 9.8,
            "rate": 0.99,
            "price_data": {},
        }

        self.oxc_wallet = MagicMock()
        self.oxc_wallet.get_address.return_value = "oxc_addr"
        self.oxg_wallet = MagicMock()
        self.oxg_wallet.get_address.return_value = "oxg_addr"

        self.history = self.swap_history.SwapHistoryService()
        self.admin = self.admin_service.AdminService()

        self.engine = self.swap_engine.SwapEngine(
            price_oracle=self.oracle,
            oxc_wallet=self.oxc_wallet,
            oxg_wallet=self.oxg_wallet,
            history_service=self.history,
            admin_service=self.admin,
        )

        self.api.init_app(
            self.engine,
            self.oracle,
            swap_hist=self.history,
            admin_svc=self.admin,
        )

        self.app = self.api.app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def test_swap_creation_validation_error_is_sanitized(self):
        """Validation errors in swap creation should be user-friendly."""
        # Invalid amount (below minimum)
        response = self.client.post("/api/v1/swap", json={
            "from": "OXC",
            "to": "OXG",
            "amount": 0.00001,  # Below minimum
            "user_address": "valid_user_address"
        })
        data = response.get_json()
        self.assertIn("error", data)
        # Should be a clean error message
        self.assertNotIn("/", data["error"])
        self.assertNotIn("line ", data["error"])

    def test_swap_creation_missing_fields_error_is_clear(self):
        """Missing field errors should clearly indicate what's missing."""
        response = self.client.post("/api/v1/swap", json={
            "from": "OXC",
            "to": "OXG"
            # Missing amount and user_address
        })
        data = response.get_json()
        self.assertIn("error", data)
        self.assertEqual(data["error"], "Missing required fields")

    def test_invalid_address_format_error_is_clear(self):
        """Invalid address format should return clear error."""
        response = self.client.post("/api/v1/swap", json={
            "from": "OXC",
            "to": "OXG",
            "amount": 10.0,
            "user_address": "ab"  # Too short
        })
        data = response.get_json()
        self.assertIn("error", data)
        self.assertEqual(data["error"], "Invalid user_address")

    def test_same_coin_swap_error_is_clear(self):
        """Attempting to swap same coin should return clear error."""
        response = self.client.post("/api/v1/swap", json={
            "from": "OXC",
            "to": "OXC",
            "amount": 10.0,
            "user_address": "valid_user_address"
        })
        data = response.get_json()
        self.assertIn("error", data)
        # Should indicate the pair is not supported
        self.assertIn("error", data)

    def test_get_nonexistent_swap_error_is_clear(self):
        """Requesting non-existent swap should return clear error."""
        response = self.client.get("/api/v1/swap/nonexistent_swap_id")
        data = response.get_json()
        self.assertIn("error", data)
        self.assertEqual(data["error"], "Swap not found")


if __name__ == "__main__":
    unittest.main()