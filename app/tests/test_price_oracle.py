import sys
import os
import unittest
import tempfile
import importlib
from unittest.mock import Mock, patch

_swap_service_path = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "swap-service"
)
if _swap_service_path not in sys.path:
    sys.path.insert(0, _swap_service_path)


class TestPriceOracleCrossRate(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["DB_PATH"] = os.path.join(self._tmpdir.name, "test.db")
        os.environ["TESTING_MODE"] = "false"

        for mod in ("config", "price_oracle"):
            if mod in sys.modules:
                del sys.modules[mod]

    def test_oxc_to_oxg_rate_is_cross_rate(self):
        price_oracle = importlib.import_module("price_oracle")
        oracle = price_oracle.PriceOracle()
        oracle._price_cache = {}

        with patch.object(oracle, "get_public_tickers") as mock_tickers:
            mock_tickers.return_value = [
                {"ticker_id": "OXC_USDT", "last_price": "0.06"},
                {"ticker_id": "OXG_USDT", "last_price": "0.03"},
            ]
            price_data = oracle.get_price("OXC", "OXG")

        expected_rate = 0.06 / 0.03
        self.assertAlmostEqual(price_data["price"], expected_rate, places=4)

    def test_oxg_to_oxc_rate_is_inverse_cross_rate(self):
        price_oracle = importlib.import_module("price_oracle")
        oracle = price_oracle.PriceOracle()
        oracle._price_cache = {}

        with patch.object(oracle, "get_public_tickers") as mock_tickers:
            mock_tickers.return_value = [
                {"ticker_id": "OXC_USDT", "last_price": "0.06"},
                {"ticker_id": "OXG_USDT", "last_price": "0.03"},
            ]
            price_data = oracle.get_price("OXG", "OXC")

        expected_rate = 0.03 / 0.06
        self.assertAlmostEqual(price_data["price"], expected_rate, places=4)

    def test_oxc_to_oxg_rate_inverse_of_oxg_to_oxc(self):
        price_oracle = importlib.import_module("price_oracle")
        oracle = price_oracle.PriceOracle()
        oracle._price_cache = {}

        with patch.object(oracle, "get_public_tickers") as mock_tickers:
            mock_tickers.return_value = [
                {"ticker_id": "OXC_USDT", "last_price": "0.06"},
                {"ticker_id": "OXG_USDT", "last_price": "0.03"},
            ]
            oxc_to_oxg = oracle.get_price("OXC", "OXG")
            oracle._price_cache = {}
            oxg_to_oxc = oracle.get_price("OXG", "OXC")

        self.assertAlmostEqual(oxc_to_oxg["price"], 1.0 / oxg_to_oxc["price"], places=4)

    def test_conversion_amount_uses_correct_rate_oxc_to_oxg(self):
        price_oracle = importlib.import_module("price_oracle")
        oracle = price_oracle.PriceOracle()
        oracle._price_cache = {}

        with patch.object(oracle, "get_public_tickers") as mock_tickers:
            mock_tickers.return_value = [
                {"ticker_id": "OXC_USDT", "last_price": "0.06"},
                {"ticker_id": "OXG_USDT", "last_price": "0.03"},
            ]
            conversion = oracle.get_conversion_amount("OXC", "OXG", 10.0, 1.0, min_fee_oxc=0, min_fee_oxg=0)

        expected_rate = 0.06 / 0.03
        expected_to_amount = 10.0 * expected_rate
        expected_fee = expected_to_amount * 0.01
        expected_net = expected_to_amount - expected_fee

        self.assertAlmostEqual(conversion["rate"], expected_rate, places=4)
        self.assertAlmostEqual(conversion["to_amount"], expected_to_amount, places=4)
        self.assertAlmostEqual(conversion["fee_amount"], expected_fee, places=4)
        self.assertAlmostEqual(conversion["net_amount"], expected_net, places=4)

    def test_conversion_amount_uses_correct_rate_oxg_to_oxc(self):
        price_oracle = importlib.import_module("price_oracle")
        oracle = price_oracle.PriceOracle()
        oracle._price_cache = {}

        with patch.object(oracle, "get_public_tickers") as mock_tickers:
            mock_tickers.return_value = [
                {"ticker_id": "OXC_USDT", "last_price": "0.06"},
                {"ticker_id": "OXG_USDT", "last_price": "0.03"},
            ]
            conversion = oracle.get_conversion_amount("OXG", "OXC", 10.0, 1.0, min_fee_oxc=0, min_fee_oxg=0)

        expected_rate = 0.03 / 0.06
        expected_to_amount = 10.0 * expected_rate
        expected_fee = expected_to_amount * 0.01
        expected_net = expected_to_amount - expected_fee

        self.assertAlmostEqual(conversion["rate"], expected_rate, places=4)
        self.assertAlmostEqual(conversion["to_amount"], expected_to_amount, places=4)
        self.assertAlmostEqual(conversion["fee_amount"], expected_fee, places=4)
        self.assertAlmostEqual(conversion["net_amount"], expected_net, places=4)

    def test_backend_does_not_trust_frontend_rates(self):
        for mod in ("config", "swap_engine", "wallet_rpc", "swap_history"):
            if mod in sys.modules:
                del sys.modules[mod]

        import importlib

        price_oracle = importlib.import_module("price_oracle")
        swap_engine = importlib.import_module("swap_engine")

        oracle = price_oracle.PriceOracle()
        oracle._price_cache = {}

        with patch.object(oracle, "get_public_tickers") as mock_tickers:
            mock_tickers.return_value = [
                {"ticker_id": "OXC_USDT", "last_price": "0.06"},
                {"ticker_id": "OXG_USDT", "last_price": "0.03"},
            ]

            mock_wallet = Mock()
            mock_wallet.get_address.return_value = "test_addr"
            mock_wallet.get_transaction.return_value = {"confirmations": 0}
            mock_wallet.get_balance.return_value = 1000.0
            mock_wallet.rpc = Mock()
            mock_wallet.rpc.get_new_address.return_value = "mock_addr"

            mock_history = Mock()
            mock_history.get_swaps_by_statuses.return_value = []
            mock_history.save_swap = Mock()
            mock_history.update_swap = Mock()

            engine = swap_engine.SwapEngine(
                price_oracle=oracle,
                oxc_wallet=mock_wallet,
                oxg_wallet=mock_wallet,
                history_service=mock_history,
                fee_percent=1.0,
                min_amount=0.0001,
                max_amount=10000.0,
                min_fee_oxc=0.0,
                min_fee_oxg=0.0,
            )

            quote = engine.create_swap_quote("OXG", "OXC", 10.0)

            expected_rate = 0.03 / 0.06
            expected_to_amount = 10.0 * expected_rate
            expected_fee = expected_to_amount * 0.01
            expected_net = expected_to_amount - expected_fee

            self.assertAlmostEqual(quote["rate"], expected_rate, places=4)
            self.assertAlmostEqual(quote["to_amount"], expected_to_amount, places=4)
            self.assertAlmostEqual(quote["fee_amount"], expected_fee, places=4)
            self.assertAlmostEqual(quote["net_amount"], expected_net, places=4)
