"""
Unit tests for reconciliation functions.

Tests cover:
- reconcile_full_history() - Test all categorization logic
- settle_orphaned_transaction() - Test fee calculations and edge cases
- refund_orphaned_transaction() - Test refund logic
"""

import os
import sys
import unittest
import tempfile
import importlib
import json
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

# Add swap-service to path
_swap_service_path = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "swap-service"
)
if _swap_service_path not in sys.path:
    sys.path.insert(0, _swap_service_path)


class TestReconcileFullHistory(unittest.TestCase):
    """Test the reconcile_full_history function."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["DB_PATH"] = os.path.join(self._tmpdir.name, "test.db")
        os.environ["TESTING_MODE"] = "true"

        # Setup test database
        from test_helpers import setup_test_db
        setup_test_db(os.environ["DB_PATH"])

        # Force reload of modules
        for mod in ["config", "swap_engine", "swap_history", "admin_service"]:
            if mod in sys.modules:
                del sys.modules[mod]

        self.swap_engine = importlib.import_module("swap_engine")
        self.swap_history = importlib.import_module("swap_history")
        self.admin_service = importlib.import_module("admin_service")
        self.SwapStatus = self.swap_engine.SwapStatus

        self.history = self.swap_history.SwapHistoryService()
        self.admin = self.admin_service.AdminService()
        
        # Mock admin methods needed for reconciliation
        self.admin.list_wallets = MagicMock(return_value={})
        self.admin.is_transaction_acknowledged = MagicMock(return_value=False)
        self.admin.acknowledge_transaction = MagicMock(return_value=True)
        self.admin.get_wallet_actions = MagicMock(return_value=[])

        # Create mock oracle and wallets
        self.oracle = MagicMock()
        self.oracle.get_conversion_amount.return_value = {
            "to_amount": 9.9,
            "fee_amount": 0.1,
            "net_amount": 9.8,
            "rate": 0.99,
            "price_data": {},
        }

        self.oxc_wallet = MagicMock()
        self.oxc_wallet.get_address.return_value = "oxc_deposit_addr"
        self.oxc_wallet.send.return_value = "oxc_settle_txid"
        self.oxc_wallet.get_balance.return_value = 1000.0
        self.oxc_wallet.rpc = MagicMock()
        self.oxc_wallet.rpc.list_transactions.return_value = []
        self.oxc_wallet.rpc.list_unspent.return_value = []

        self.oxg_wallet = MagicMock()
        self.oxg_wallet.get_address.return_value = "oxg_deposit_addr"
        self.oxg_wallet.send.return_value = "oxg_settle_txid"
        self.oxg_wallet.get_balance.return_value = 1000.0
        self.oxg_wallet.rpc = MagicMock()
        self.oxg_wallet.rpc.list_transactions.return_value = []
        self.oxg_wallet.rpc.list_unspent.return_value = []

        self.engine = self.swap_engine.SwapEngine(
            price_oracle=self.oracle,
            oxc_wallet=self.oxc_wallet,
            oxg_wallet=self.oxg_wallet,
            history_service=self.history,
            admin_service=self.admin,
        )

    def test_reconcile_returns_expected_structure(self):
        """reconcile_full_history should return expected structure."""
        results = self.engine.reconcile_full_history(count=10)
        
        self.assertIn("scanned_count", results)
        self.assertIn("unaccounted_deposits", results)
        self.assertIn("unaccounted_withdrawals", results)
        self.assertIn("mismatched_amounts", results)
        self.assertIn("late_deposits", results)
        self.assertIn("acknowledged_deposits", results)
        self.assertIn("matched_swaps_count", results)
        self.assertIn("coin_stats", results)
        
        self.assertIsInstance(results["unaccounted_deposits"], list)
        self.assertIsInstance(results["unaccounted_withdrawals"], list)
        self.assertIsInstance(results["mismatched_amounts"], list)
        self.assertIsInstance(results["late_deposits"], list)

    def test_reconcile_coin_stats_initialized(self):
        """Coin stats should be initialized for all supported coins."""
        results = self.engine.reconcile_full_history(count=10)
        
        self.assertIn("OXC", results["coin_stats"])
        self.assertIn("OXG", results["coin_stats"])
        self.assertIn("total_received", results["coin_stats"]["OXC"])
        self.assertIn("total_sent", results["coin_stats"]["OXC"])

    def test_reconcile_handles_empty_wallet_history(self):
        """Reconciliation should handle empty wallet history gracefully."""
        # Wallets return empty transaction lists by default
        results = self.engine.reconcile_full_history(count=10)
        
        self.assertEqual(results["scanned_count"], 0)
        self.assertEqual(len(results["unaccounted_deposits"]), 0)
        self.assertEqual(len(results["unaccounted_withdrawals"]), 0)

    def test_reconcile_categorizes_admin_wallet_transactions(self):
        """Transactions to admin wallets should be categorized as ADMIN_WALLET."""
        # Setup: Create admin wallet address
        admin_addr = "admin_liquidity_addr"
        self.admin.list_wallets = MagicMock(return_value={
            "OXC": {"liquidity": {"address": admin_addr}}
        })
        
        # Mock wallet transactions including admin address
        txs = [
            {
                "txid": "admin_tx_1",
                "category": "receive",
                "address": admin_addr,
                "amount": 100.0,
            }
        ]
        self.oxc_wallet.rpc.list_transactions.return_value = txs
        
        results = self.engine.reconcile_full_history(count=10)
        
        # Should be in acknowledged_deposits
        admin_txs = [t for t in results["acknowledged_deposits"] 
                     if t.get("category") == "ADMIN_WALLET"]
        self.assertEqual(len(admin_txs), 1)
        self.assertEqual(admin_txs[0]["txid"], "admin_tx_1")

    def test_reconcile_categorizes_acknowledged_transactions(self):
        """Acknowledged transactions should be in acknowledged_deposits."""
        # Setup: Acknowledge a transaction
        self.admin.acknowledge_transaction = MagicMock(return_value=True)
        self.admin.is_transaction_acknowledged = MagicMock(return_value=True)
        
        txs = [
            {
                "txid": "acknowledged_tx",
                "category": "receive",
                "address": "some_addr",
                "amount": 50.0,
            }
        ]
        self.oxc_wallet.rpc.list_transactions.return_value = txs
        
        results = self.engine.reconcile_full_history(count=10)
        
        # Should be in acknowledged_deposits
        ack_txs = [t for t in results["acknowledged_deposits"] 
                   if t.get("txid") == "acknowledged_tx"]
        self.assertEqual(len(ack_txs), 1)

    def test_reconcile_detects_matched_swaps(self):
        """Transactions matching swaps should be counted as matched."""
        # Create a swap and complete it normally
        swap = self.engine.create_swap("OXC", "OXG", 10.0, "user_addr_recon")
        # Update the swap to completed with withdrawal_txid
        self.history.update_swap(swap["swap_id"], {
            "withdrawal_txid": "withdrawal_tx_1",
            "status": "completed",
        })
        
        # Mock transactions including the swap withdrawal
        txs = [
            {
                "txid": "withdrawal_tx_1",
                "category": "send",
                "address": "user_addr_recon",
                "amount": 9.8,
            }
        ]
        self.oxg_wallet.rpc.list_transactions.return_value = txs
        
        results = self.engine.reconcile_full_history(count=10)
        
        self.assertGreater(results["matched_swaps_count"], 0)

    def test_reconcile_detects_late_deposits(self):
        """Deposits to expired/cancelled swaps should be detected as late."""
        # Create and expire a swap
        swap = self.engine.create_swap("OXC", "OXG", 10.0, "user_addr_late")
        self.history.update_swap(swap["swap_id"], {
            "status": "expired",
        })
        
        # Mock transaction to the swap's deposit address
        txs = [
            {
                "txid": "late_deposit_tx",
                "category": "receive",
                "address": swap["deposit_address"],
                "amount": 10.0,
            }
        ]
        self.oxc_wallet.rpc.list_transactions.return_value = txs
        
        results = self.engine.reconcile_full_history(count=10)
        
        self.assertEqual(len(results["late_deposits"]), 1)
        self.assertEqual(results["late_deposits"][0]["swap_id"], swap["swap_id"])

    def test_reconcile_detects_mismatched_amounts(self):
        """Deposits with different amounts than expected should be detected."""
        # Create a swap
        swap = self.engine.create_swap("OXC", "OXG", 10.0, "user_addr_mismatch")
        
        # Mock transaction with different amount
        txs = [
            {
                "txid": "mismatch_tx",
                "category": "receive",
                "address": swap["deposit_address"],
                "amount": 15.0,  # Different from expected 10.0
            }
        ]
        self.oxc_wallet.rpc.list_transactions.return_value = txs
        
        results = self.engine.reconcile_full_history(count=10)
        
        self.assertEqual(len(results["mismatched_amounts"]), 1)
        self.assertEqual(results["mismatched_amounts"][0]["type"], "SURPLUS")

    def test_reconcile_detects_insufficient_amount(self):
        """Deposits with less than expected should be detected as INSUFFICIENT."""
        # Create a swap
        swap = self.engine.create_swap("OXC", "OXG", 10.0, "user_addr_insufficient")
        
        # Mock transaction with less amount
        txs = [
            {
                "txid": "insufficient_tx",
                "category": "receive",
                "address": swap["deposit_address"],
                "amount": 5.0,  # Less than expected 10.0
            }
        ]
        self.oxc_wallet.rpc.list_transactions.return_value = txs
        
        results = self.engine.reconcile_full_history(count=10)
        
        self.assertEqual(len(results["mismatched_amounts"]), 1)
        self.assertEqual(results["mismatched_amounts"][0]["type"], "INSUFFICIENT")

    def test_reconcile_detects_unaccounted_withdrawals(self):
        """Withdrawals not matching any swap should be detected as unaccounted."""
        # Mock transaction that doesn't match any swap
        txs = [
            {
                "txid": "unknown_withdrawal_tx",
                "category": "send",
                "address": "unknown_addr",
                "amount": 50.0,
            }
        ]
        self.oxc_wallet.rpc.list_transactions.return_value = txs
        self.admin.get_wallet_actions.return_value = []
        
        results = self.engine.reconcile_full_history(count=10)
        
        self.assertEqual(len(results["unaccounted_withdrawals"]), 1)
        self.assertEqual(results["unaccounted_withdrawals"][0]["txid"], "unknown_withdrawal_tx")


class TestSettleOrphanedTransaction(unittest.TestCase):
    """Test the settle_orphaned_transaction function."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["DB_PATH"] = os.path.join(self._tmpdir.name, "test.db")
        os.environ["TESTING_MODE"] = "true"

        # Setup test database
        from test_helpers import setup_test_db
        setup_test_db(os.environ["DB_PATH"])

        # Force reload of modules
        for mod in ["config", "swap_engine", "swap_history", "admin_service"]:
            if mod in sys.modules:
                del sys.modules[mod]

        self.swap_engine = importlib.import_module("swap_engine")
        self.swap_history = importlib.import_module("swap_history")
        self.admin_service = importlib.import_module("admin_service")

        self.history = self.swap_history.SwapHistoryService()
        self.admin = self.admin_service.AdminService()
        
        # Mock admin methods needed for settlement
        self.admin.is_transaction_acknowledged = MagicMock(return_value=False)
        self.admin.acknowledge_transaction = MagicMock(return_value=True)

        # Create mock oracle and wallets
        self.oracle = MagicMock()
        self.oracle.get_conversion_amount.return_value = {
            "to_amount": 9.9,
            "fee_amount": 0.1,
            "net_amount": 9.8,
            "rate": 0.99,
            "price_data": {},
        }

        self.oxc_wallet = MagicMock()
        self.oxc_wallet.get_address.return_value = "oxc_deposit_addr"
        self.oxc_wallet.send.return_value = "oxc_settle_txid"
        self.oxc_wallet.get_balance.return_value = 1000.0
        self.oxc_wallet.get_transaction.return_value = {"amount": 10.0, "confirmations": 6}

        self.oxg_wallet = MagicMock()
        self.oxg_wallet.get_address.return_value = "oxg_deposit_addr"
        self.oxg_wallet.send.return_value = "oxg_settle_txid"
        self.oxg_wallet.get_balance.return_value = 1000.0

        self.engine = self.swap_engine.SwapEngine(
            price_oracle=self.oracle,
            oxc_wallet=self.oxc_wallet,
            oxg_wallet=self.oxg_wallet,
            history_service=self.history,
            admin_service=self.admin,
        )

    def test_settle_orphaned_returns_txid(self):
        """settle_orphaned_transaction should return transaction ID."""
        result = self.engine.settle_orphaned_transaction(
            txid="orphan_tx_1",
            coin="OXC",
            amount=10.0,
            user_address="user_target_addr",
            username="admin",
        )
        
        self.assertIn("txid", result)
        self.assertIn("net_amount", result)
        self.assertIn("target_coin", result)

    def test_settle_orphaned_applies_fees(self):
        """settle_orphaned_transaction should apply fees correctly."""
        # Setup oracle to return specific fee
        self.oracle.get_conversion_amount.return_value = {
            "to_amount": 9.5,
            "fee_amount": 0.5,
            "net_amount": 9.0,
            "rate": 0.95,
            "price_data": {},
        }
        
        result = self.engine.settle_orphaned_transaction(
            txid="orphan_tx_2",
            coin="OXC",
            amount=10.0,
            user_address="user_target_addr",
            username="admin",
        )
        
        # Net amount should be after fees
        self.assertEqual(result["net_amount"], 9.0)

    def test_settle_orphaned_rejects_acknowledged_transactions(self):
        """settle_orphaned_transaction should reject already acknowledged transactions."""
        self.admin.is_transaction_acknowledged = MagicMock(return_value=True)
        
        with self.assertRaises(self.swap_engine.SwapError) as ctx:
            self.engine.settle_orphaned_transaction(
                txid="already_acknowledged_tx",
                coin="OXC",
                amount=10.0,
                user_address="user_target_addr",
                username="admin",
            )
        
        self.assertIn("already been acknowledged", str(ctx.exception))

    def test_settle_orphaned_rejects_zero_amount(self):
        """settle_orphaned_transaction should reject zero amount."""
        self.oracle.get_conversion_amount.return_value = {
            "to_amount": 0,
            "fee_amount": 0,
            "net_amount": 0,
            "rate": 1.0,
            "price_data": {},
        }
        
        with self.assertRaises(self.swap_engine.InvalidAmountError):
            self.engine.settle_orphaned_transaction(
                txid="zero_amount_tx",
                coin="OXC",
                amount=0.0,
                user_address="user_target_addr",
                username="admin",
            )

    def test_settle_orphaned_updates_swap(self):
        """settle_orphaned_transaction should update associated swap if provided."""
        # Create a swap
        swap = self.engine.create_swap("OXC", "OXG", 10.0, "user_addr_settle")
        swap_id = swap["swap_id"]
        
        result = self.engine.settle_orphaned_transaction(
            txid="orphan_tx_3",
            coin="OXC",
            amount=10.0,
            user_address="user_addr_settle",
            username="admin",
            swap_id=swap_id,
        )
        
        # Verify swap was updated
        updated_swap = self.history.get_swap(swap_id)
        self.assertEqual(updated_swap["status"], "completed")
        self.assertEqual(updated_swap["withdrawal_txid"], result["txid"])

    def test_settle_orphaned_determines_target_coin(self):
        """settle_orphaned_transaction should determine target coin from swap."""
        # Create a swap OXC -> OXG
        swap = self.engine.create_swap("OXC", "OXG", 10.0, "user_addr_target")
        swap_id = swap["swap_id"]
        
        result = self.engine.settle_orphaned_transaction(
            txid="orphan_tx_4",
            coin="OXC",
            amount=10.0,
            user_address="user_addr_target",
            username="admin",
            swap_id=swap_id,
        )
        
        # Target coin should be OXG (from the swap)
        self.assertEqual(result["target_coin"], "OXG")


class TestRefundOrphanedTransaction(unittest.TestCase):
    """Test the refund_orphaned_transaction function."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["DB_PATH"] = os.path.join(self._tmpdir.name, "test.db")
        os.environ["TESTING_MODE"] = "true"

        # Setup test database
        from test_helpers import setup_test_db
        setup_test_db(os.environ["DB_PATH"])

        # Force reload of modules
        for mod in ["config", "swap_engine", "swap_history", "admin_service"]:
            if mod in sys.modules:
                del sys.modules[mod]

        self.swap_engine = importlib.import_module("swap_engine")
        self.swap_history = importlib.import_module("swap_history")
        self.admin_service = importlib.import_module("admin_service")

        self.history = self.swap_history.SwapHistoryService()
        self.admin = self.admin_service.AdminService()
        
        # Mock admin methods needed for refund
        self.admin.is_transaction_acknowledged = MagicMock(return_value=False)
        self.admin.acknowledge_transaction = MagicMock(return_value=True)

        # Create mock oracle and wallets
        self.oracle = MagicMock()
        self.oracle.get_conversion_amount.return_value = {
            "to_amount": 9.9,
            "fee_amount": 0.1,
            "net_amount": 9.8,
            "rate": 0.99,
            "price_data": {},
        }

        self.oxc_wallet = MagicMock()
        self.oxc_wallet.get_address.return_value = "oxc_deposit_addr"
        self.oxc_wallet.send.return_value = "oxc_refund_txid"
        self.oxc_wallet.get_balance.return_value = 1000.0
        self.oxc_wallet.get_transaction.return_value = {"amount": 10.0, "confirmations": 6}

        self.oxg_wallet = MagicMock()
        self.oxg_wallet.get_address.return_value = "oxg_deposit_addr"
        self.oxg_wallet.send.return_value = "oxg_refund_txid"
        self.oxg_wallet.get_balance.return_value = 1000.0

        self.engine = self.swap_engine.SwapEngine(
            price_oracle=self.oracle,
            oxc_wallet=self.oxc_wallet,
            oxg_wallet=self.oxg_wallet,
            history_service=self.history,
            admin_service=self.admin,
        )

    def test_refund_orphaned_returns_txid(self):
        """refund_orphaned_transaction should return transaction ID."""
        result = self.engine.refund_orphaned_transaction(
            txid="refund_tx_1",
            coin="OXC",
            amount=10.0,
            target_address="refund_target_addr",
            username="admin",
        )
        
        self.assertIn("txid", result)
        self.assertIn("refund_amount", result)

    def test_refund_orphaned_applies_processing_fee(self):
        """refund_orphaned_transaction should deduct processing fee."""
        result = self.engine.refund_orphaned_transaction(
            txid="refund_tx_2",
            coin="OXC",
            amount=100.0,
            target_address="refund_target_addr",
            username="admin",
        )
        
        # Should deduct 1% processing fee (or minimum fee)
        # 100 * 0.99 = 99.0 (minus any minimum fee adjustment)
        self.assertLessEqual(result["refund_amount"], 100.0)
        self.assertGreater(result["refund_amount"], 98.0)  # Should be close to 99

    def test_refund_orphaned_rejects_acknowledged_transactions(self):
        """refund_orphaned_transaction should reject already acknowledged transactions."""
        self.admin.is_transaction_acknowledged = MagicMock(return_value=True)
        
        with self.assertRaises(self.swap_engine.SwapError) as ctx:
            self.engine.refund_orphaned_transaction(
                txid="already_acknowledged_tx",
                coin="OXC",
                amount=10.0,
                target_address="refund_target_addr",
                username="admin",
            )
        
        self.assertIn("already been acknowledged", str(ctx.exception))

    def test_refund_orphaned_rejects_too_small_amount(self):
        """refund_orphaned_transaction should reject amounts too small after fees."""
        # Very small amount that would be zero after fees
        with self.assertRaises(self.swap_engine.InvalidAmountError):
            self.engine.refund_orphaned_transaction(
                txid="too_small_tx",
                coin="OXC",
                amount=0.00000001,
                target_address="refund_target_addr",
                username="admin",
            )

    def test_refund_orphaned_uses_minimum_fee_when_applicable(self):
        """refund_orphaned_transaction should use minimum fee when 1% is too small."""
        # Set an amount where 1% would be less than minimum fee (1.0)
        # Amount of 50.0 -> 1% = 0.5, which is less than min_fee_oxc (1.0)
        # So min_fee (1.0) will be used, refund = 50.0 - 1.0 = 49.0
        result = self.engine.refund_orphaned_transaction(
            txid="small_tx",
            coin="OXC",
            amount=50.0,
            target_address="refund_target_addr",
            username="admin",
        )
        
        # Should still return a valid result (minimum fee applied)
        self.assertIn("txid", result)
        # Refund should be 49.0 (50 - 1.0 min fee)
        self.assertEqual(result["refund_amount"], 49.0)


if __name__ == "__main__":
    unittest.main()