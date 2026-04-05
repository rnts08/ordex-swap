import os
import sys
import unittest
import json
import logging
import io

_swap_service_path = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "swap-service"
)
if _swap_service_path not in sys.path:
    sys.path.insert(0, _swap_service_path)


class TestStructuredLogging(unittest.TestCase):
    def setUp(self):
        from structured_logging import StructuredLogger, StructuredFormatter

        self.logger = StructuredLogger("test")
        self.output = io.StringIO()
        handler = logging.StreamHandler(self.output)
        handler.setFormatter(StructuredFormatter())

        root_logger = logging.getLogger("test")
        root_logger.setLevel(logging.DEBUG)
        root_logger.handlers = []
        root_logger.addHandler(handler)

    def test_structured_logger_info_with_extra(self):
        self.logger.info("Test message", user="admin", action="login")

        output = self.output.getvalue()
        log_data = json.loads(output)

        self.assertEqual(log_data["message"], "Test message")
        self.assertEqual(log_data["extra"]["user"], "admin")
        self.assertEqual(log_data["extra"]["action"], "login")

    def test_structured_logger_error_with_extra(self):
        self.logger.error("Error occurred", error="connection_failed")

        output = self.output.getvalue()
        log_data = json.loads(output)

        self.assertEqual(log_data["level"], "ERROR")
        self.assertEqual(log_data["extra"]["error"], "connection_failed")

    def test_structured_logger_warning(self):
        self.logger.warning("Warning message", code=404)

        output = self.output.getvalue()
        log_data = json.loads(output)

        self.assertEqual(log_data["level"], "WARNING")
        self.assertEqual(log_data["extra"]["code"], 404)

    def test_structured_logger_debug(self):
        self.logger.debug("Debug message", trace_id="abc123")

        output = self.output.getvalue()
        log_data = json.loads(output)

        self.assertEqual(log_data["level"], "DEBUG")
        self.assertEqual(log_data["extra"]["trace_id"], "abc123")

    def test_structured_logger_exception(self):
        try:
            raise ValueError("test error")
        except ValueError:
            self.logger.exception("Exception occurred", error_code="VAL_ERR")

        output = self.output.getvalue()
        log_data = json.loads(output)

        self.assertEqual(log_data["level"], "ERROR")
        self.assertIn("exception", log_data)


class TestErrorSanitization(unittest.TestCase):
    def setUp(self):
        os.environ["TESTING_MODE"] = "true"

        for mod in ("config",):
            if mod in sys.modules:
                del sys.modules[mod]

        import importlib

        importlib.import_module("config")

    def test_sanitize_error_message_with_safe_patterns(self):
        from api import sanitize_error_message

        class FakeError(Exception):
            pass

        # "invalid amount provided" contains "Invalid amount" which is in the allowlist
        e = FakeError("invalid amount provided")
        result = sanitize_error_message(e, "Validation failed")
        # Should return the allowlisted version
        self.assertEqual(result, "Invalid amount")

    def test_sanitize_error_message_with_long_message(self):
        from api import sanitize_error_message

        class FakeError(Exception):
            pass

        e = FakeError("x" * 200)
        result = sanitize_error_message(e, "Validation failed")
        self.assertEqual(result, "Validation failed")

    def test_sanitize_error_message_with_unsafe_pattern(self):
        from api import sanitize_error_message

        class FakeError(Exception):
            pass

        e = FakeError("internal server error at line 42")
        result = sanitize_error_message(e, "Operation failed")
        self.assertEqual(result, "Operation failed")

    def test_sanitize_error_message_with_empty_message(self):
        from api import sanitize_error_message

        class FakeError(Exception):
            pass

        e = FakeError("")
        result = sanitize_error_message(e, "Default message")
        self.assertEqual(result, "Default message")

    def test_sanitize_error_message_with_must_be_pattern(self):
        from api import sanitize_error_message

        class FakeError(Exception):
            pass

        # "must be" is no longer in safe prefixes, so this should return default
        e = FakeError("amount must be greater than 0")
        result = sanitize_error_message(e, "Validation failed")
        self.assertEqual(result, "Validation failed")


if __name__ == "__main__":
    unittest.main()
