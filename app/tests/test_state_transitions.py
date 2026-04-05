"""
Unit tests for swap state transitions.

Tests verify that:
1. Valid state transitions are allowed
2. Invalid state transitions are rejected
3. Admin override can bypass state transition rules
4. Terminal states cannot be transitioned from (except by admin)
"""

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

from swap_engine import SwapStatus, VALID_STATE_TRANSITIONS, TERMINAL_STATES, ACTIVE_STATES, ADMIN_INTERVENTION_STATES


class TestStateTransitions(unittest.TestCase):
    """Test the state transition map and validation."""

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
        self.SwapError = self.swap_engine.SwapError

        self.history = self.swap_history.SwapHistoryService()
        self.admin = self.admin_service.AdminService()

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

    def test_valid_state_transitions_map_exists(self):
        """Verify the state transition map is defined."""
        self.assertIsNotNone(VALID_STATE_TRANSITIONS)
        self.assertIsInstance(VALID_STATE_TRANSITIONS, dict)

    def test_all_statuses_have_transitions_defined(self):
        """Every status should have an entry in the transition map."""
        for status in SwapStatus:
            self.assertIn(status.value, VALID_STATE_TRANSITIONS,
                f"Status {status.value} missing from transition map")

    def test_terminal_states_have_no_outgoing_transitions(self):
        """Terminal states should have empty transition sets."""
        for status in TERMINAL_STATES:
            transitions = VALID_STATE_TRANSITIONS.get(status, None)
            self.assertIsNotNone(transitions, f"Terminal state {status} should be in map")
            self.assertEqual(len(transitions), 0,
                f"Terminal state {status} should have no outgoing transitions")

    def test_pending_can_transition_to_valid_states(self):
        """PENDING should be able to transition to expected states."""
        pending_transitions = VALID_STATE_TRANSITIONS[SwapStatus.PENDING.value]
        
        expected_valid = {
            SwapStatus.AWAITING_DEPOSIT.value,
            SwapStatus.PROCESSING.value,
            SwapStatus.CANCELLED.value,
            SwapStatus.EXPIRED.value,
            SwapStatus.TIMED_OUT.value,
            SwapStatus.CIRCUIT_BREAKER.value,
            SwapStatus.INVALID.value,
        }
        self.assertEqual(pending_transitions, expected_valid)

    def test_processing_can_transition_to_valid_states(self):
        """PROCESSING should be able to transition to expected states."""
        processing_transitions = VALID_STATE_TRANSITIONS[SwapStatus.PROCESSING.value]
        
        expected_valid = {
            SwapStatus.COMPLETED.value,
            SwapStatus.DELAYED.value,
            SwapStatus.FAILED.value,
            SwapStatus.INVALID.value,
        }
        self.assertEqual(processing_transitions, expected_valid)

    def test_delayed_can_transition_to_valid_states(self):
        """DELAYED should be able to transition to expected states."""
        delayed_transitions = VALID_STATE_TRANSITIONS[SwapStatus.DELAYED.value]
        
        expected_valid = {
            SwapStatus.COMPLETED.value,
            SwapStatus.FAILED.value,
            SwapStatus.CANCELLED.value,
            SwapStatus.INVALID.value,
        }
        self.assertEqual(delayed_transitions, expected_valid)

    def test_late_deposit_can_transition_to_valid_states(self):
        """LATE_DEPOSIT should be able to transition to expected states."""
        late_deposit_transitions = VALID_STATE_TRANSITIONS[SwapStatus.LATE_DEPOSIT.value]
        
        expected_valid = {
            SwapStatus.RECONCILED.value,
            SwapStatus.COMPLETED.value,
            SwapStatus.CANCELLED.value,
            SwapStatus.INVALID.value,
        }
        self.assertEqual(late_deposit_transitions, expected_valid)

    def test_circuit_breaker_can_transition_to_valid_states(self):
        """CIRCUIT_BREAKER should be able to transition to expected states."""
        circuit_breaker_transitions = VALID_STATE_TRANSITIONS[SwapStatus.CIRCUIT_BREAKER.value]
        
        expected_valid = {
            SwapStatus.COMPLETED.value,
            SwapStatus.CANCELLED.value,
            SwapStatus.INVALID.value,
        }
        self.assertEqual(circuit_breaker_transitions, expected_valid)

    def test_completed_is_terminal(self):
        """COMPLETED should be a terminal state."""
        self.assertIn(SwapStatus.COMPLETED.value, TERMINAL_STATES)
        self.assertNotIn(SwapStatus.COMPLETED.value, ACTIVE_STATES)

    def test_failed_is_terminal(self):
        """FAILED should be a terminal state."""
        self.assertIn(SwapStatus.FAILED.value, TERMINAL_STATES)
        self.assertNotIn(SwapStatus.FAILED.value, ACTIVE_STATES)

    def test_cancelled_is_terminal(self):
        """CANCELLED should be a terminal state."""
        self.assertIn(SwapStatus.CANCELLED.value, TERMINAL_STATES)
        self.assertNotIn(SwapStatus.CANCELLED.value, ACTIVE_STATES)

    def test_expired_is_terminal(self):
        """EXPIRED should be a terminal state."""
        self.assertIn(SwapStatus.EXPIRED.value, TERMINAL_STATES)
        self.assertNotIn(SwapStatus.EXPIRED.value, ACTIVE_STATES)

    def test_timed_out_is_terminal(self):
        """TIMED_OUT should be a terminal state."""
        self.assertIn(SwapStatus.TIMED_OUT.value, TERMINAL_STATES)
        self.assertNotIn(SwapStatus.TIMED_OUT.value, ACTIVE_STATES)

    def test_reconciled_is_terminal(self):
        """RECONCILED should be a terminal state."""
        self.assertIn(SwapStatus.RECONCILED.value, TERMINAL_STATES)
        self.assertNotIn(SwapStatus.RECONCILED.value, ACTIVE_STATES)

    def test_invalid_is_terminal(self):
        """INVALID should be a terminal state."""
        self.assertIn(SwapStatus.INVALID.value, TERMINAL_STATES)
        self.assertNotIn(SwapStatus.INVALID.value, ACTIVE_STATES)

    def test_pending_is_active(self):
        """PENDING should be an active state."""
        self.assertIn(SwapStatus.PENDING.value, ACTIVE_STATES)
        self.assertNotIn(SwapStatus.PENDING.value, TERMINAL_STATES)

    def test_awaiting_deposit_is_active(self):
        """AWAITING_DEPOSIT should be an active state."""
        self.assertIn(SwapStatus.AWAITING_DEPOSIT.value, ACTIVE_STATES)
        self.assertNotIn(SwapStatus.AWAITING_DEPOSIT.value, TERMINAL_STATES)

    def test_processing_is_active(self):
        """PROCESSING should be an active state."""
        self.assertIn(SwapStatus.PROCESSING.value, ACTIVE_STATES)
        self.assertNotIn(SwapStatus.PROCESSING.value, TERMINAL_STATES)

    def test_delayed_is_active(self):
        """DELAYED should be an active state."""
        self.assertIn(SwapStatus.DELAYED.value, ACTIVE_STATES)
        self.assertNotIn(SwapStatus.DELAYED.value, TERMINAL_STATES)

    def test_circuit_breaker_is_active(self):
        """CIRCUIT_BREAKER should be an active state."""
        self.assertIn(SwapStatus.CIRCUIT_BREAKER.value, ACTIVE_STATES)
        self.assertNotIn(SwapStatus.CIRCUIT_BREAKER.value, TERMINAL_STATES)

    def test_admin_can_override_terminal_states(self):
        """Admin should be able to set any status, even on terminal states."""
        swap = self.engine.create_swap("OXC", "OXG", 10.0, "user_addr_terminal")
        swap_id = swap["swap_id"]
        
        # Set to completed
        self.engine.set_swap_status(swap_id, "completed", performed_by="admin")
        
        # Admin should still be able to change it
        updated = self.engine.set_swap_status(swap_id, "cancelled", performed_by="admin", reason="Changed mind")
        self.assertEqual(updated["status"], "cancelled")
        self.assertTrue(updated["admin_override"])

    def test_admin_override_prevents_further_changes(self):
        """Once admin sets a terminal state with override, background jobs should not change it."""
        swap = self.engine.create_swap("OXC", "OXG", 10.0, "user_addr_override")
        swap_id = swap["swap_id"]
        
        # Admin sets to cancelled with override
        self.engine.set_swap_status(swap_id, "cancelled", performed_by="admin")
        
        # Verify override is set
        fetched = self.history.get_swap(swap_id)
        self.assertTrue(fetched["admin_override"])
        self.assertEqual(fetched["admin_set_state"], "cancelled")

    def test_clear_override_restores_normal_processing(self):
        """Clearing admin override should allow normal processing to resume."""
        swap = self.engine.create_swap("OXC", "OXG", 10.0, "user_addr_clear")
        swap_id = swap["swap_id"]
        
        # Admin sets to cancelled with override
        self.engine.set_swap_status(swap_id, "cancelled", performed_by="admin")
        
        # Clear the override
        cleared = self.engine.clear_admin_override(swap_id)
        self.assertFalse(cleared["admin_override"])
        self.assertIsNone(cleared["admin_set_state"])
        
        # Status should still be cancelled, but override is cleared
        self.assertEqual(cleared["status"], "cancelled")

    def test_late_deposit_is_not_terminal(self):
        """LATE_DEPOSIT should not be in terminal states (requires admin intervention)."""
        self.assertNotIn(SwapStatus.LATE_DEPOSIT.value, TERMINAL_STATES)
        self.assertIn(SwapStatus.LATE_DEPOSIT.value, ADMIN_INTERVENTION_STATES)

    def test_circuit_breaker_requires_admin_intervention(self):
        """CIRCUIT_BREAKER should be in admin intervention states."""
        self.assertIn(SwapStatus.CIRCUIT_BREAKER.value, ADMIN_INTERVENTION_STATES)


if __name__ == "__main__":
    unittest.main()