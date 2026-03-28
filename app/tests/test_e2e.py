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


class FakeOracle:
    def get_conversion_amount(self, from_coin, to_coin, amount, fee_percent):
        rate = 2.0 if from_coin == "OXC" else 0.5
        to_amount = amount * rate
        fee = to_amount * (fee_percent / 100)
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
    def __init__(self, coin):
        self.coin = coin

    def get_address(self):
        return f"{self.coin.lower()}_addr"

    def send(self, _address, _amount):
        return f"tx_{self.coin.lower()}"

    def get_balance(self):
        return 100.0


class TestE2EApiFlow(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["DB_PATH"] = os.path.join(self._tmpdir.name, "test.db")
        os.environ["TESTING_MODE"] = "true"

        for mod in (
            "config",
            "api",
            "swap_engine",
            "swap_history",
            "price_history",
        ):
            if mod in sys.modules:
                del sys.modules[mod]

        api = importlib.import_module("api")
        swap_engine = importlib.import_module("swap_engine")
        swap_history = importlib.import_module("swap_history")
        price_history = importlib.import_module("price_history")

        self.db_path = os.environ["DB_PATH"]
        self.oracle = FakeOracle()
        self.oxc_wallet = FakeWallet("OXC")
        self.oxg_wallet = FakeWallet("OXG")

        self.history_service = swap_history.SwapHistoryService()
        self.price_history = price_history.PriceHistoryService(self.oracle)

        engine = swap_engine.SwapEngine(
            price_oracle=self.oracle,
            oxc_wallet=self.oxc_wallet,
            oxg_wallet=self.oxg_wallet,
            history_service=self.history_service,
            fee_percent=1.0,
        )

        api.init_app(engine, self.oracle, self.price_history, self.history_service)
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


if __name__ == "__main__":
    unittest.main()
