import os
import sys
import unittest
import tempfile
import importlib
from unittest.mock import MagicMock

# Add swap-service to path
_swap_service_path = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "swap-service"
)
if _swap_service_path not in sys.path:
    sys.path.insert(0, _swap_service_path)

class TestAdminTransactionScan(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["DB_PATH"] = os.path.join(self._tmpdir.name, "test.db")
        os.environ["TESTING_MODE"] = "true"

        # Force reload of modules to ensure clean state
        for mod in ["config", "swap_engine", "swap_history", "price_oracle", "wallet_rpc"]:
            if mod in sys.modules:
                del sys.modules[mod]

        self.swap_engine = importlib.import_module("swap_engine")
        self.swap_history = importlib.import_module("swap_history")
        self.price_oracle = importlib.import_module("price_oracle")
        self.wallet_rpc = importlib.import_module("wallet_rpc")

        self.history = self.swap_history.SwapHistoryService()
        self.oracle = MagicMock()
        self.oxc_wallet = MagicMock()
        self.oxg_wallet = MagicMock()

        self.engine = self.swap_engine.SwapEngine(
            price_oracle=self.oracle,
            oxc_wallet=self.oxc_wallet,
            oxg_wallet=self.oxg_wallet,
            history_service=self.history
        )

    def test_scan_identifies_liquidity_topup(self):
        # Mock admin wallets
        admin_wallets = {
            "OXC": {
                "liquidity": {"address": "oxc_liq_addr", "updated_at": "..."}
            }
        }
        
        # Mock UTXOs from node
        self.oxc_wallet.rpc.list_unspent.return_value = [
            {"txid": "tx1", "address": "oxc_liq_addr", "amount": 10.0}
        ]
        self.oxg_wallet.rpc.list_unspent.return_value = []
        
        results = self.engine.get_unaccounted_transactions(admin_wallets)
        
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["category"], "LIQUIDITY_TOPUP")
        self.assertEqual(results[0]["purpose"], "liquidity")
        self.assertEqual(results[0]["amount"], 10.0)

    def test_scan_identifies_orphan_deposit(self):
        # Create a timed out swap in history
        swap_id = "test_swap_123"
        address = "swap_deposit_addr"
        self.history.add_swap({
            "swap_id": swap_id,
            "status": "timed_out",
            "deposit_address": address,
            "from_coin": "OXC",
            "from_amount": 1.0
        })
        self.history.update_swap(swap_id, {"status": "timed_out"})

        # Mock UTXOs
        self.oxc_wallet.rpc.list_unspent.return_value = [
            {"txid": "tx2", "address": address, "amount": 1.0}
        ]
        self.oxg_wallet.rpc.list_unspent.return_value = []
        
        results = self.engine.get_unaccounted_transactions({})
        
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["category"], "ORPHAN_DEPOSIT")
        self.assertEqual(results[0]["swap_id"], swap_id)
        self.assertEqual(results[0]["swap_status"], "timed_out")

    def test_scan_skips_accounted_swaps(self):
        # Create a completed swap
        address = "completed_addr"
        self.history.add_swap({
            "swap_id": "completed_swap",
            "status": "completed",
            "deposit_address": address
        })
        self.history.update_swap("completed_swap", {"status": "completed"})

        # Mock UTXOs
        self.oxc_wallet.rpc.list_unspent.return_value = [
            {"txid": "tx3", "address": address, "amount": 1.0}
        ]
        self.oxg_wallet.rpc.list_unspent.return_value = []
        
        results = self.engine.get_unaccounted_transactions({})
        
        # Should be empty because it's accounted for
        self.assertEqual(len(results), 0)

    def test_scan_identifies_unknown_transaction(self):
        # Mock unknown UTXO
        self.oxc_wallet.rpc.list_unspent.return_value = [
            {"txid": "tx4", "address": "unknown_addr", "amount": 0.5}
        ]
        self.oxg_wallet.rpc.list_unspent.return_value = []
        
        results = self.engine.get_unaccounted_transactions({})
        
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["category"], "UNKNOWN")
        self.assertEqual(results[0]["address"], "unknown_addr")

if __name__ == "__main__":
    unittest.main()
