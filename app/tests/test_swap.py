import sys
import os
import unittest
import tempfile
import importlib
from unittest.mock import Mock
from datetime import datetime, timezone

# Add swap-service to path BEFORE any imports
_swap_service_path = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "swap-service"
)
if _swap_service_path not in sys.path:
    sys.path.insert(0, _swap_service_path)


class TestSwapEngine(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["DB_PATH"] = os.path.join(self._tmpdir.name, "test.db")
        os.environ["TESTING_MODE"] = "false"
        os.environ["SWAP_CONFIRMATIONS_REQUIRED"] = "0"

        for mod in ("config", "swap_engine", "swap_history"):
            if mod in sys.modules:
                del sys.modules[mod]

        config = importlib.import_module("config")
        self.config = config
        swap_engine = importlib.import_module("swap_engine")
        swap_history = importlib.import_module("swap_history")
        wallet_rpc = importlib.import_module("wallet_rpc")

        self.SwapEngine = swap_engine.SwapEngine
        self.SwapError = swap_engine.SwapError
        self.InvalidAmountError = swap_engine.InvalidAmountError
        self.UnsupportedPairError = swap_engine.UnsupportedPairError
        self.LiquidityHoldError = swap_engine.LiquidityHoldError
        self.SwapHistoryService = swap_history.SwapHistoryService
        self.WalletRPCError = wallet_rpc.WalletRPCError

        self.oracle = Mock()
        self.oxc_wallet = Mock()
        self.oxg_wallet = Mock()

        self.test_history = self.SwapHistoryService()

        now = datetime.now(timezone.utc)
        self.oracle.get_conversion_amount.return_value = {
            "to_amount": 99.0,
            "fee_amount": 1.0,
            "net_amount": 98.0,
            "rate": 100.0,
            "price_data": {"price": 100.0, "timestamp": now.isoformat()},
        }

        self.oxc_wallet.get_address.return_value = "oxc_deposit_addr"
        self.oxg_wallet.get_address.return_value = "oxg_deposit_addr"
        self.oxc_wallet.get_transaction.return_value = {
            "confirmations": self.config.SWAP_CONFIRMATIONS_REQUIRED
        }
        self.oxg_wallet.get_transaction.return_value = {
            "confirmations": self.config.SWAP_CONFIRMATIONS_REQUIRED
        }

        self.engine = self.SwapEngine(
            price_oracle=self.oracle,
            oxc_wallet=self.oxc_wallet,
            oxg_wallet=self.oxg_wallet,
            history_service=self.test_history,
            fee_percent=1.0,
            min_amount=0.0001,
            max_amount=10000.0,
        )

    def test_validate_swap_request_valid(self):
        self.engine.validate_swap_request("OXC", "OXG", 10.0)

    def test_validate_swap_unsupported_pair(self):
        with self.assertRaises(self.UnsupportedPairError):
            self.engine.validate_swap_request("OXC", "BTC", 10.0)

    def test_validate_swap_same_coin(self):
        with self.assertRaises(self.UnsupportedPairError):
            self.engine.validate_swap_request("OXC", "OXC", 10.0)

    def test_validate_swap_below_min(self):
        with self.assertRaises(self.InvalidAmountError):
            self.engine.validate_swap_request("OXC", "OXG", 0.00001)

    def test_validate_swap_above_max(self):
        with self.assertRaises(self.InvalidAmountError):
            self.engine.validate_swap_request("OXC", "OXG", 20000.0)

    def test_get_deposit_address_oxc(self):
        addr = self.engine.get_deposit_address("OXC")
        self.assertEqual(addr, "oxc_deposit_addr")

    def test_get_deposit_address_oxg(self):
        addr = self.engine.get_deposit_address("OXG")
        self.assertEqual(addr, "oxg_deposit_addr")

    def test_get_deposit_address_unknown(self):
        with self.assertRaises(self.UnsupportedPairError):
            self.engine.get_deposit_address("BTC")

    def test_create_swap_quote(self):
        quote = self.engine.create_swap_quote("OXC", "OXG", 10.0)

        self.assertIn("quote_id", quote)
        self.assertEqual(quote["from_coin"], "OXC")
        self.assertEqual(quote["to_coin"], "OXG")
        self.assertEqual(quote["from_amount"], 10.0)
        self.assertEqual(quote["fee_percent"], 1.0)

    def test_create_swap(self):
        swap = self.engine.create_swap("OXC", "OXG", 10.0, "user_address")

        self.assertIn("swap_id", swap)
        self.assertEqual(swap["from_coin"], "OXC")
        self.assertEqual(swap["to_coin"], "OXG")
        self.assertEqual(swap["user_address"], "user_address")
        self.assertEqual(swap["status"], "pending")

    def test_get_swap(self):
        swap = self.engine.create_swap("OXC", "OXG", 10.0, "user_address")
        swap_id = swap["swap_id"]

        retrieved = self.engine.get_swap(swap_id)
        self.assertEqual(retrieved["swap_id"], swap_id)

    def test_get_swap_not_found(self):
        result = self.engine.get_swap("non-existent")
        self.assertIsNone(result)

    def test_confirm_deposit(self):
        swap = self.engine.create_swap("OXC", "OXG", 10.0, "user_address")
        swap_id = swap["swap_id"]

        self.oxg_wallet.send.return_value = "txid_abc123"

        confirmed = self.engine.confirm_deposit(swap_id, "deposit_txid")

        self.assertEqual(confirmed["status"], "completed")
        if self.config.TESTING_MODE:
            self.oxg_wallet.send.assert_not_called()
            self.assertTrue(str(confirmed["settle_txid"]).startswith("tx_test_mock_"))
        else:
            self.oxg_wallet.send.assert_called_once()

    def test_confirm_deposit_invalid_state(self):
        swap = self.engine.create_swap("OXC", "OXG", 10.0, "user_address")
        swap_id = swap["swap_id"]

        self.engine.confirm_deposit(swap_id, "deposit_txid")

        with self.assertRaises(self.SwapError):
            self.engine.confirm_deposit(swap_id, "another_txid")

    def test_confirm_deposit_late_deposit(self):
        swap = self.engine.create_swap("OXC", "OXG", 10.0, "user_address")
        swap_id = swap["swap_id"]

        # Simulate expiration
        swap["status"] = "expired"
        self.test_history.update_swap(swap_id, swap)
        if swap_id in self.engine._pending_swaps:
            del self.engine._pending_swaps[swap_id]

        # Intercept late deposit
        late = self.engine.confirm_deposit(swap_id, "late_deposit_txid")

        self.assertEqual(late["status"], "late_deposit")
        self.assertEqual(late["deposit_txid"], "late_deposit_txid")
        self.assertNotIn(swap_id, self.engine._pending_swaps)

        history_obj = self.test_history.get_swap(swap_id)
        self.assertEqual(history_obj["status"], "late_deposit")

    def test_cancel_swap_late_deposit(self):
        swap = self.engine.create_swap("OXC", "OXG", 10.0, "user_address")
        swap_id = swap["swap_id"]

        swap["status"] = "late_deposit"
        self.test_history.update_swap(swap_id, swap)
        if swap_id in self.engine._pending_swaps:
            del self.engine._pending_swaps[swap_id]

        cancelled = self.engine.cancel_swap(swap_id)

        self.assertEqual(cancelled["status"], "cancelled")
        history_obj = self.test_history.get_swap(swap_id)
        self.assertEqual(history_obj["status"], "cancelled")

    def test_confirm_deposit_delayed_on_low_liquidity(self):
        swap = self.engine.create_swap("OXC", "OXG", 10.0, "user_address")
        swap_id = swap["swap_id"]

        self.oxg_wallet.send.side_effect = self.WalletRPCError("insufficient funds")

        delayed = self.engine.confirm_deposit(swap_id, "deposit_txid")

        self.assertEqual(delayed["status"], "delayed")
        self.assertEqual(delayed["delay_code"], "liquidity_low")

    def test_delayed_swap_is_queued_and_completes_later(self):
        swap = self.engine.create_swap("OXC", "OXG", 10.0, "user_address")
        swap_id = swap["swap_id"]

        self.oxg_wallet.send.side_effect = self.WalletRPCError("balance too low")
        delayed = self.engine.confirm_deposit(swap_id, "deposit_txid")
        self.assertEqual(delayed["status"], "delayed")

        self.oxg_wallet.send.side_effect = None
        self.oxg_wallet.send.return_value = "txid_ok"

        processed = self.engine.process_delayed_swaps()
        self.assertEqual(processed, 1)
        completed = self.engine.get_swap(swap_id)
        self.assertEqual(completed["status"], "completed")

    def test_liquidity_hold_blocks_higher_amount_swaps(self):
        def conversion(
            from_coin, to_coin, amount, fee_percent, min_fee_oxc=None, min_fee_oxg=None
        ):
            to_amount = amount * 2.0
            fee_amount = to_amount * (fee_percent / 100)
            if fee_amount < (min_fee_oxg if to_coin == "OXG" else min_fee_oxc):
                fee_amount = min_fee_oxg if to_coin == "OXG" else min_fee_oxc
            net_amount = to_amount - fee_amount
            now = datetime.now(timezone.utc)
            return {
                "to_amount": to_amount,
                "fee_amount": fee_amount,
                "net_amount": net_amount,
                "rate": 2.0,
                "price_data": {"price": 2.0, "timestamp": now.isoformat()},
            }

        self.oracle.get_conversion_amount.side_effect = conversion

        swap = self.engine.create_swap("OXC", "OXG", 10.0, "user_address")
        swap_id = swap["swap_id"]
        self.oxg_wallet.send.side_effect = self.WalletRPCError("insufficient balance")
        delayed = self.engine.confirm_deposit(swap_id, "deposit_txid")
        self.assertEqual(delayed["status"], "delayed")

        blocked_quote = self.engine.create_swap_quote("OXC", "OXG", 12.0)
        self.assertTrue(blocked_quote["liquidity_blocked"])

        with self.assertRaises(self.LiquidityHoldError):
            self.engine.create_swap("OXC", "OXG", 12.0, "user_address")

    def test_cancel_swap(self):
        swap = self.engine.create_swap("OXC", "OXG", 10.0, "user_address")
        swap_id = swap["swap_id"]

        cancelled = self.engine.cancel_swap(swap_id)

        self.assertEqual(cancelled["status"], "cancelled")

    def test_cancel_swap_without_deposit(self):
        swap = self.engine.create_swap("OXG", "OXC", 5.0, "user_address")
        swap_id = swap["swap_id"]

        cancelled = self.engine.cancel_swap(swap_id)

        self.assertEqual(cancelled["status"], "cancelled")
        self.assertIsNone(cancelled.get("deposit_txid"))

    def test_cancel_completed_swap_fails(self):
        swap = self.engine.create_swap("OXC", "OXG", 10.0, "user_address")
        swap_id = swap["swap_id"]

        self.oxg_wallet.send.return_value = "txid_abc123"
        self.engine.confirm_deposit(swap_id, "deposit_txid")

        with self.assertRaises(self.SwapError):
            self.engine.cancel_swap(swap_id)

    def test_list_swaps(self):
        self.engine.create_swap("OXC", "OXG", 10.0, "user1")
        self.engine.create_swap("OXG", "OXC", 20.0, "user2")

        swaps = self.engine.list_swaps()
        self.assertEqual(len(swaps), 2)

    def test_list_swaps_filtered(self):
        swap = self.engine.create_swap("OXC", "OXG", 10.0, "user1")
        swap_id = swap["swap_id"]

        self.oxg_wallet.send.return_value = "txid_abc123"
        self.engine.confirm_deposit(swap_id, "deposit_txid")

        self.engine.create_swap("OXG", "OXC", 20.0, "user2")

        completed = self.engine.list_swaps("completed")
        self.assertEqual(len(completed), 1)

    def test_get_balance(self):
        self.oxc_wallet.get_balance.return_value = 100.5
        self.oxg_wallet.get_balance.return_value = 50.25

        oxc_bal = self.engine.get_balance("OXC")
        oxg_bal = self.engine.get_balance("OXG")

        self.assertEqual(oxc_bal, 100.5)
        self.assertEqual(oxg_bal, 50.25)


class TestSwapEngineFeeCalculation(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["DB_PATH"] = os.path.join(self._tmpdir.name, "test.db")

        for mod in ("config", "swap_engine", "swap_history"):
            if mod in sys.modules:
                del sys.modules[mod]

        self.oracle = Mock()
        self.oxc_wallet = Mock()
        self.oxg_wallet = Mock()

    def test_fee_calculation_1_percent(self):
        now = datetime.now(timezone.utc)
        self.oracle.get_conversion_amount.return_value = {
            "to_amount": 100.0,
            "fee_amount": 1.0,
            "net_amount": 99.0,
            "rate": 10.0,
            "price_data": {"price": 10.0, "timestamp": now.isoformat()},
        }
        self.oxc_wallet.get_address.return_value = "oxc_deposit_addr"

        swap_engine = importlib.import_module("swap_engine")
        engine = swap_engine.SwapEngine(
            price_oracle=self.oracle,
            oxc_wallet=self.oxc_wallet,
            oxg_wallet=self.oxg_wallet,
            fee_percent=1.0,
        )

        swap = engine.create_swap("OXC", "OXG", 10.0, "user_addr")

        self.assertEqual(swap["fee_amount"], 1.0)
        self.assertEqual(swap["net_amount"], 99.0)


class TestMinFeeEnforcement(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["DB_PATH"] = os.path.join(self._tmpdir.name, "test.db")
        os.environ["TESTING_MODE"] = "false"
        os.environ["SWAP_CONFIRMATIONS_REQUIRED"] = "0"

        for mod in ("config", "swap_engine", "swap_history"):
            if mod in sys.modules:
                del sys.modules[mod]

        swap_history = importlib.import_module("swap_history")
        self.SwapHistoryService = swap_history.SwapHistoryService

    def test_min_fee_enforced_oxc_to_oxg(self):
        import price_oracle

        oracle = price_oracle.PriceOracle()

        swap_engine = importlib.import_module("swap_engine")

        oxc_wallet = Mock()
        oxg_wallet = Mock()
        oxc_wallet.get_address.return_value = "oxc_addr"
        oxg_wallet.get_address.return_value = "oxg_addr"

        history = self.SwapHistoryService()

        engine = swap_engine.SwapEngine(
            price_oracle=oracle,
            oxc_wallet=oxc_wallet,
            oxg_wallet=oxg_wallet,
            history_service=history,
            fee_percent=1.0,
            min_amount=0.0001,
            max_amount=10000.0,
            min_fee_oxc=1.0,
            min_fee_oxg=1.0,
        )

        quote = engine.create_swap_quote("OXC", "OXG", 1.0)

        self.assertGreaterEqual(quote["fee_amount"], 1.0)
        self.assertEqual(quote["fee_amount"], 1.0)

    def test_min_fee_enforced_oxg_to_oxc(self):
        import price_oracle

        oracle = price_oracle.PriceOracle()

        swap_engine = importlib.import_module("swap_engine")

        oxc_wallet = Mock()
        oxg_wallet = Mock()
        oxc_wallet.get_address.return_value = "oxc_addr"
        oxg_wallet.get_address.return_value = "oxg_addr"

        history = self.SwapHistoryService()

        engine = swap_engine.SwapEngine(
            price_oracle=oracle,
            oxc_wallet=oxc_wallet,
            oxg_wallet=oxg_wallet,
            history_service=history,
            fee_percent=1.0,
            min_amount=0.0001,
            max_amount=10000.0,
            min_fee_oxc=1.0,
            min_fee_oxg=1.0,
        )

        quote = engine.create_swap_quote("OXG", "OXC", 100.0)

        self.assertGreaterEqual(quote["fee_amount"], 1.0)
        self.assertEqual(quote["fee_amount"], 1.0)

    def test_fee_percentage_applied_when_higher_than_min(self):
        import price_oracle

        oracle = price_oracle.PriceOracle()

        swap_engine = importlib.import_module("swap_engine")

        oxc_wallet = Mock()
        oxg_wallet = Mock()
        oxc_wallet.get_address.return_value = "oxc_addr"
        oxg_wallet.get_address.return_value = "oxg_addr"

        history = self.SwapHistoryService()

        engine = swap_engine.SwapEngine(
            price_oracle=oracle,
            oxc_wallet=oxc_wallet,
            oxg_wallet=oxg_wallet,
            history_service=history,
            fee_percent=2.0,
            min_amount=0.0001,
            max_amount=10000.0,
            min_fee_oxc=0.5,
            min_fee_oxg=0.5,
        )

        quote = engine.create_swap_quote("OXC", "OXG", 100.0)

        expected_fee = quote["to_amount"] * 2.0 / 100.0
        self.assertGreater(quote["fee_amount"], 0.5)

    def test_min_fee_takes_precedence_when_percentage_fee_is_lower(self):
        import price_oracle

        oracle = price_oracle.PriceOracle()

        swap_engine = importlib.import_module("swap_engine")

        oxc_wallet = Mock()
        oxg_wallet = Mock()
        oxc_wallet.get_address.return_value = "oxc_addr"
        oxg_wallet.get_address.return_value = "oxg_addr"

        history = self.SwapHistoryService()

        engine = swap_engine.SwapEngine(
            price_oracle=oracle,
            oxc_wallet=oxc_wallet,
            oxg_wallet=oxg_wallet,
            history_service=history,
            fee_percent=0.1,
            min_amount=0.0001,
            max_amount=10000.0,
            min_fee_oxc=5.0,
            min_fee_oxg=5.0,
        )

        quote = engine.create_swap_quote("OXC", "OXG", 100.0)

        self.assertGreaterEqual(quote["fee_amount"], 5.0)
        self.assertEqual(quote["fee_amount"], 5.0)

    def test_negative_net_amount_rejected_by_validation(self):
        import price_oracle

        oracle = price_oracle.PriceOracle()

        swap_engine = importlib.import_module("swap_engine")

        oxc_wallet = Mock()
        oxg_wallet = Mock()
        oxc_wallet.get_address.return_value = "oxc_addr"
        oxg_wallet.get_address.return_value = "oxg_addr"

        history = self.SwapHistoryService()

        engine = swap_engine.SwapEngine(
            price_oracle=oracle,
            oxc_wallet=oxc_wallet,
            oxg_wallet=oxg_wallet,
            history_service=history,
            fee_percent=99.0,
            min_amount=0.0001,
            max_amount=10000.0,
            min_fee_oxc=1.0,
            min_fee_oxg=1.0,
        )

        with self.assertRaises(swap_engine.InvalidAmountError) as ctx:
            engine.validate_swap_request("OXC", "OXG", 0.001)

        self.assertIn("zero or negative", str(ctx.exception).lower())
        self.assertIn("Fee too high", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
