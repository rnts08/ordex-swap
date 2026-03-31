import os
import sys
import unittest
import tempfile
import importlib
from unittest.mock import MagicMock
from datetime import datetime, timezone

# Add swap-service to path
_swap_service_path = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "swap-service"
)
if _swap_service_path not in sys.path:
    sys.path.insert(0, _swap_service_path)

class TestLateDepositSettle(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["DB_PATH"] = os.path.join(self._tmpdir.name, "test.db")
        os.environ["TESTING_MODE"] = "true"

        for mod in ["config", "swap_engine", "swap_history", "price_oracle", "wallet_rpc"]:
            if mod in sys.modules:
                del sys.modules[mod]

        self.swap_engine = importlib.import_module("swap_engine")
        self.swap_history = importlib.import_module("swap_history")
        self.price_oracle = importlib.import_module("price_oracle")
        
        self.SwapStatus = self.swap_engine.SwapStatus
        self.InvalidAmountError = self.swap_engine.InvalidAmountError

        self.history = self.swap_history.SwapHistoryService()
        self.oracle = MagicMock()
        self.oxc_wallet = MagicMock()
        self.oxg_wallet = MagicMock()

        self.engine = self.swap_engine.SwapEngine(
            price_oracle=self.oracle,
            oxc_wallet=self.oxc_wallet,
            oxg_wallet=self.oxg_wallet,
            history_service=self.history,
            fee_percent=1.0,
            min_fee_oxc=0.1,
            min_fee_oxg=0.1
        )

    def test_recalculates_late_deposit_on_settle(self):
        # 1. Create an expired swap
        swap_id = "expired_swap"
        address = "deposit_addr"
        user_addr = "user_dest_addr"
        
        original_swap = {
            "swap_id": swap_id,
            "status": self.SwapStatus.TIMED_OUT.value,
            "deposit_address": address,
            "user_address": user_addr,
            "from_coin": "OXC",
            "to_coin": "OXG",
            "from_amount": 1.0,  # Original quote for 1.0
            "net_amount": 0.9,    # Original net
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        self.history.add_swap(original_swap)
        self.history.update_swap(swap_id, {"status": "timed_out"})

        # 2. Confirm a LATE_DEPOSIT with DIFFERENT amount (e.g. 2.0)
        # Mock get_transaction to return 2.0 received at that address
        self.oxc_wallet.get_transaction.return_value = {
            "txid": "late_tx",
            "details": [
                {"category": "receive", "address": address, "amount": 2.0}
            ]
        }
        
        self.engine.confirm_deposit(swap_id, "late_tx")
        
        updated_swap = self.history.get_swap(swap_id)
        self.assertEqual(updated_swap["status"], "late_deposit")
        self.assertEqual(updated_swap["from_amount"], 2.0)

        # 3. Settle it. It should recalculate based on 2.0
        # Mock oracle for 2.0 OXC -> OXG conversion
        # 2.0 - 1% fee (0.02) = 1.98. Rate 1:1 for simplicity.
        self.oracle.get_conversion_amount.return_value = {
            "to_amount": 2.0,
            "fee_amount": 0.02,
            "net_amount": 1.98,
            "rate": 1.0,
            "price_data": {}
        }
        
        # We need to disable TESTING_MODE temporarily to verify the send call parameters
        import swap_engine
        original_testing_mode = swap_engine.TESTING_MODE
        swap_engine.TESTING_MODE = False
        try:
            settled = self.engine._settle_swap(swap_id)
        finally:
            swap_engine.TESTING_MODE = original_testing_mode
        
        self.assertEqual(settled["status"], "completed")
        self.assertEqual(settled["net_amount"], 1.98)
        self.oxg_wallet.send.assert_called_with(user_addr, 1.98)

    def test_fails_settle_if_late_amount_too_small(self):
        swap_id = "fail_swap"
        address = "fail_addr"
        
        self.history.add_swap({
            "swap_id": swap_id,
            "status": "timed_out",
            "deposit_address": address,
            "user_address": "user_dest_addr",
            "from_coin": "OXC",
            "to_coin": "OXG",
            "from_amount": 1.0
        })
        self.history.update_swap(swap_id, {"status": "timed_out"})

        # Late deposit of very small amount (e.g. 0.01)
        self.oxc_wallet.get_transaction.return_value = {
            "txid": "tiny_tx",
            "details": [{"category": "receive", "address": address, "amount": 0.01}]
        }
        self.engine.confirm_deposit(swap_id, "tiny_tx")
        
        # Oracle returns net_amount <= 0 because fee (min 0.1) > 0.01
        self.oracle.get_conversion_amount.return_value = {
            "to_amount": 0.01,
            "fee_amount": 0.1,
            "net_amount": -0.09,
            "rate": 1.0,
            "price_data": {}
        }
        
        with self.assertRaises(self.InvalidAmountError) as cm:
            self.engine._settle_swap(swap_id)
        
        self.assertIn("Calculation failed for received amount", str(cm.exception))

if __name__ == "__main__":
    unittest.main()
