import tempfile
import unittest
from pathlib import Path

from paper.mobile_control_plane import (
    ApprovalLedger, SignalStateStore, make_proposal, process_mobile_callback,
    sign_approval, size_linear_position,
)


class MobileControlPlaneTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "approvals.sqlite3"
        self.secret = b"unit-test-secret-not-for-production-32bytes!"
        self.sizing = size_linear_position(
            equity=10000, risk_fraction=0.01, entry=100, stop=98,
            target=104, side="LONG", lot_size=1,
            value_per_price_unit=1, estimated_cost_per_unit=0.1,
        )
        self.proposal = make_proposal(
            instrument="TEST", sizing=self.sizing, source="unit-test",
            created_at=1000, ttl_seconds=60,
        )
        self.ledger = ApprovalLedger(self.path, self.secret)

    def tearDown(self):
        self.tmp.cleanup()

    def test_size_respects_risk_budget_and_lot(self):
        self.assertTrue(self.sizing["size_valid"])
        self.assertLessEqual(self.sizing["estimated_risk"], 100)
        self.assertEqual(self.sizing["quantity"] % 1, 0)
        self.assertFalse(self.sizing["real_orders"])

    def test_rejects_risk_over_one_percent(self):
        with self.assertRaises(ValueError):
            size_linear_position(equity=1000, risk_fraction=0.02, entry=100,
                stop=99, target=102, side="LONG")

    def test_rejects_wrong_stop_direction(self):
        with self.assertRaises(ValueError):
            size_linear_position(equity=1000, risk_fraction=0.01, entry=100,
                stop=101, target=102, side="LONG")

    def test_signed_approval_is_one_use_and_never_submits(self):
        callback = sign_approval(self.proposal, self.secret)
        result = self.ledger.consume(self.proposal, callback, now=1020)
        self.assertEqual(result["decision"], "APPROVE")
        self.assertFalse(result["broker_action_taken"])
        self.assertFalse(result["real_orders"])
        with self.assertRaisesRegex(ValueError, "already consumed"):
            self.ledger.consume(self.proposal, callback, now=1021)

    def test_tampered_callback_rejected(self):
        callback = sign_approval(self.proposal, self.secret)
        callback["action"] = "KILL"
        with self.assertRaisesRegex(ValueError, "signature"):
            self.ledger.consume(self.proposal, callback, now=1020)

    def test_expired_callback_rejected(self):
        callback = sign_approval(self.proposal, self.secret)
        with self.assertRaisesRegex(ValueError, "expired"):
            self.ledger.consume(self.proposal, callback, now=1061)

    def test_wrong_proposal_rejected(self):
        callback = sign_approval(self.proposal, self.secret)
        other = dict(self.proposal, proposal_id="different")
        with self.assertRaisesRegex(ValueError, "ID mismatch"):
            self.ledger.consume(other, callback, now=1020)

    def test_dismiss_and_kill_are_non_execution_decisions(self):
        for action in ("DISMISS", "KILL"):
            callback = sign_approval(self.proposal, self.secret, action=action)
            result = self.ledger.consume(self.proposal, callback, now=1020)
            self.assertEqual(result["decision"], action)
            self.assertFalse(result["broker_action_taken"])
        self.assertTrue(self.ledger.is_killed())

    def test_proposal_payload_tampering_rejected(self):
        callback = sign_approval(self.proposal, self.secret)
        changed = dict(self.proposal)
        changed["sizing"] = dict(self.proposal["sizing"], quantity=99999)
        with self.assertRaisesRegex(ValueError, "tampering"):
            self.ledger.consume(changed, callback, now=1020)

    def test_secret_must_be_long(self):
        with self.assertRaises(ValueError):
            ApprovalLedger(self.path, b"short")


if __name__ == "__main__":
    unittest.main()


class SignalStateStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "signals.sqlite3"
        self.store = SignalStateStore(self.path)
        sizing = size_linear_position(
            equity=10000, risk_fraction=0.005, entry=100, stop=98,
            target=104, side="LONG", lot_size=1,
        )
        self.proposal = make_proposal(
            instrument="TEST", sizing=sizing, source="unit-test",
            created_at=1000, ttl_seconds=180,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_queue_is_idempotent(self):
        first = self.store.queue(self.proposal, now=1001)
        second = self.store.queue(self.proposal, now=1002)
        self.assertEqual(first["state"], "QUEUED")
        self.assertFalse(first["idempotent"])
        self.assertTrue(second["idempotent"])
        self.assertEqual(self.store.status()["states"]["QUEUED"], 1)

    def test_approval_then_duplicate_is_idempotent(self):
        self.store.queue(self.proposal, now=1001)
        result = self.store.transition(self.proposal["proposal_id"], "APPROVED", now=1010)
        repeated = self.store.transition(self.proposal["proposal_id"], "APPROVED", now=1011)
        self.assertEqual(result["state"], "APPROVED")
        self.assertTrue(repeated["idempotent"])
        self.assertFalse(result["broker_action_taken"])

    def test_expiry_revokes_queued_proposal(self):
        self.store.queue(self.proposal, now=1001)
        expired = self.store.expire_due(now=1181)
        self.assertEqual(expired, [self.proposal["proposal_id"]])
        self.assertEqual(self.store.get(self.proposal["proposal_id"])["state"], "EXPIRED")

    def test_expired_proposal_cannot_be_approved(self):
        self.store.queue(self.proposal, now=1001)
        with self.assertRaisesRegex(ValueError, "expired"):
            self.store.transition(self.proposal["proposal_id"], "APPROVED", now=1181)

    def test_terminal_state_cannot_be_reopened(self):
        self.store.queue(self.proposal, now=1001)
        self.store.transition(self.proposal["proposal_id"], "DISMISSED", now=1010)
        with self.assertRaisesRegex(ValueError, "invalid transition"):
            self.store.transition(self.proposal["proposal_id"], "APPROVED", now=1011)

    def test_nonce_cannot_be_reused_for_transition(self):
        self.store.queue(self.proposal, now=1001)
        self.store.transition(self.proposal["proposal_id"], "APPROVED", now=1010, nonce="n1")
        # Different target transition is invalid because approval is already terminal for approval.
        with self.assertRaisesRegex(ValueError, "invalid transition"):
            self.store.transition(self.proposal["proposal_id"], "DISMISSED", now=1011, nonce="n1")

    def test_proposal_collision_rejected(self):
        self.store.queue(self.proposal, now=1001)
        changed = dict(self.proposal, proposal_hash="different")
        with self.assertRaisesRegex(ValueError, "collision"):
            self.store.queue(changed, now=1002)

    def test_kill_lock_blocks_approval(self):
        self.store.queue(self.proposal, now=1001)
        self.store.activate_kill(now=1005)
        self.assertTrue(self.store.is_killed())
        with self.assertRaisesRegex(ValueError, "KILLED->APPROVED|kill lock"):
            self.store.transition(self.proposal["proposal_id"], "APPROVED", now=1010)

    def test_kill_state_persists_across_store_restart(self):
        self.store.activate_kill(now=1005)
        restarted = SignalStateStore(self.path)
        self.assertTrue(restarted.is_killed())


class CallbackIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "control.sqlite3"
        self.secret = b"callback-integration-test-secret-32bytes"
        self.ledger = ApprovalLedger(self.path, self.secret)
        self.store = SignalStateStore(self.path)
        sizing = size_linear_position(
            equity=10000, risk_fraction=0.005, entry=100, stop=98,
            target=104, side="LONG",
        )
        self.proposal = make_proposal(
            instrument="TEST", sizing=sizing, source="integration-test",
            created_at=1000, ttl_seconds=120,
        )
        self.store.queue(self.proposal, now=1001)

    def tearDown(self):
        self.tmp.cleanup()

    def test_approval_moves_queued_to_approved_without_broker_action(self):
        callback = sign_approval(self.proposal, self.secret, action="APPROVE")
        result = process_mobile_callback(self.proposal, callback,
            ledger=self.ledger, store=self.store, now=1010)
        self.assertEqual(result["state"], "APPROVED")
        self.assertFalse(result["broker_action_taken"])
        self.assertFalse(result["real_orders"])

    def test_kill_moves_all_active_signals_to_killed(self):
        second = make_proposal(instrument="TEST2",
            sizing=self.proposal["sizing"], source="integration-test",
            created_at=1000, ttl_seconds=120)
        self.store.queue(second, now=1001)
        callback = sign_approval(self.proposal, self.secret, action="KILL")
        result = process_mobile_callback(self.proposal, callback,
            ledger=self.ledger, store=self.store, now=1010)
        self.assertTrue(result["kill_lock_active"])
        self.assertEqual(self.store.get(self.proposal["proposal_id"])["state"], "KILLED")
        self.assertEqual(self.store.get(second["proposal_id"])["state"], "KILLED")

    def test_duplicate_callback_rejected(self):
        callback = sign_approval(self.proposal, self.secret, action="APPROVE")
        process_mobile_callback(self.proposal, callback,
            ledger=self.ledger, store=self.store, now=1010)
        with self.assertRaisesRegex(ValueError, "already consumed"):
            process_mobile_callback(self.proposal, callback,
                ledger=self.ledger, store=self.store, now=1011)

    def test_separate_databases_rejected(self):
        other_store = SignalStateStore(Path(self.tmp.name) / "other.sqlite3")
        with self.assertRaisesRegex(ValueError, "share one SQLite"):
            process_mobile_callback(self.proposal, {}, ledger=self.ledger,
                                    store=other_store, now=1010)
