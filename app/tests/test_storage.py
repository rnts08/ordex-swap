import os
import sys
import unittest
import tempfile
import importlib
from datetime import datetime, timezone

# Add swap-service to path
_swap_service_path = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "swap-service"
)
if _swap_service_path not in sys.path:
    sys.path.insert(0, _swap_service_path)

from test_helpers import setup_test_db


class TestPriceOraclePersistentCache(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["DB_PATH"] = os.path.join(self._tmpdir.name, "test.db")

        setup_test_db(os.environ["DB_PATH"])

        for mod in ("config", "price_oracle"):
            if mod in sys.modules:
                del sys.modules[mod]

        self.price_oracle = importlib.import_module("price_oracle")

    def test_persistent_cache_round_trip(self):
        oracle = self.price_oracle.PriceOracle()
        now = datetime.now(timezone.utc).isoformat()
        expected = {
            "from_coin": "OXC",
            "to_coin": "OXG",
            "price": 1.23,
            "timestamp": now,
            "oxc_usdt": 0.1,
            "oxg_usdt": 0.05,
            "source": "test",
        }

        oracle._fetch_price = lambda *_args, **_kwargs: expected
        first = oracle.get_price("OXC", "OXG")
        self.assertEqual(first["price"], 1.23)

        oracle2 = self.price_oracle.PriceOracle()
        oracle2._fetch_price = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("Should use persistent cache")
        )
        cached = oracle2.get_price("OXC", "OXG")
        self.assertEqual(cached["price"], 1.23)


class TestPriceHistoryService(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["DB_PATH"] = os.path.join(self._tmpdir.name, "test.db")

        setup_test_db(os.environ["DB_PATH"])

        for mod in ("config", "price_history"):
            if mod in sys.modules:
                del sys.modules[mod]

        self.price_history = importlib.import_module("price_history")

        class FakeOracle:
            def __init__(self):
                self.calls = 0

            def get_price(self, _from_coin, _to_coin):
                self.calls += 1
                rate = 2.0 if self.calls == 1 else 4.0
                return {
                    "price": rate,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "oxc_usdt": 0.2,
                    "oxg_usdt": 0.1,
                    "source": "test",
                }

        self.oracle = FakeOracle()

    def test_history_insert_and_stats(self):
        service = self.price_history.PriceHistoryService(self.oracle)
        service.fetch_and_record()
        service.fetch_and_record()

        latest = service.get_latest()
        self.assertEqual(latest["cross_rate"], 4.0)

        history = service.get_history(limit=2)
        # Both records are in the same hour bucket, so we get 1 bucket back (average/latest).
        self.assertEqual(len(history), 1)

        stats = service.get_price_stats(hours=24)
        # Stats are based on raw data, so we verify 2 entries are recorded.
        self.assertEqual(stats["count"], 2)
        self.assertEqual(stats["min"], 2.0)
        self.assertEqual(stats["max"], 4.0)
        self.assertAlmostEqual(stats["avg"], 3.0)


class TestSwapHistoryService(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["DB_PATH"] = os.path.join(self._tmpdir.name, "test.db")

        setup_test_db(os.environ["DB_PATH"])

        for mod in ("config", "swap_history"):
            if mod in sys.modules:
                del sys.modules[mod]

        self.swap_history = importlib.import_module("swap_history")

    def test_swap_lifecycle_and_stats(self):
        service = self.swap_history.SwapHistoryService()
        swap1 = {
            "swap_id": "s1",
            "from_coin": "OXC",
            "from_amount": 10.0,
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        swap2 = {
            "swap_id": "s2",
            "from_coin": "OXG",
            "from_amount": 5.0,
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        service.add_swap(swap1)
        service.add_swap(swap2)
        service.complete_swap("s1")

        pending = service.get_pending_swaps()
        completed = service.get_completed_swaps(limit=10)

        self.assertEqual(len(pending), 1)
        self.assertEqual(len(completed), 1)
        self.assertEqual(completed[0]["swap_id"], "s1")

        stats = service.get_stats()
        self.assertEqual(stats["total_swaps"], 2)
        self.assertEqual(stats["pending_swaps"], 1)
        self.assertEqual(stats["total_volume_oxc"], 10.0)
        self.assertEqual(stats["total_volume_oxg"], 5.0)


if __name__ == "__main__":
    unittest.main()
