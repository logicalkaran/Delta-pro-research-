from __future__ import annotations

import os
import subprocess
import sys
import time
from decimal import Decimal as D

import pytest

from recovery.state_reconciler import StateReconciler
from storage.event_journal import EventJournal


def test_reconciler_rebuilds_partial_fill_and_remaining_parent_size(tmp_path):
    with EventJournal(tmp_path / "events.sqlite") as journal:
        journal.append("parent-p1", "PARENT_CREATED", {"parent_id": "p1", "quantity": "1"}, ts_ns=1)
        journal.append("dispatch-c1", "CHILD_DISPATCHED", {"parent_id": "p1", "client_order_id": "c1", "quantity": "0.4"}, ts_ns=2)
        journal.append("ack-c1", "CHILD_ACKNOWLEDGED", {"parent_id": "p1", "client_order_id": "c1"}, ts_ns=3)
        journal.append("fill-c1", "CHILD_PARTIAL_FILL", {"parent_id": "p1", "client_order_id": "c1", "fill_quantity": "0.15"}, ts_ns=4)
        recovered = StateReconciler(journal).replay()["p1"]
        assert recovered.quantity == D("1")
        assert recovered.filled_quantity == D("0.15")
        assert recovered.remaining_size == D("0.85")
        assert recovered.children[0].remaining_quantity == D("0.25")
        assert recovered.can_resume is False  # residual of a partial child still needs order-state reconciliation


def test_open_exchange_order_missing_local_ack_is_cancel_required_not_cancelled(tmp_path):
    with EventJournal(tmp_path / "events.sqlite") as journal:
        journal.append("parent-p", "PARENT_CREATED", {"parent_id": "p", "quantity": "0.2"}, ts_ns=1)
        journal.append("dispatch-c", "CHILD_DISPATCHED", {"parent_id": "p", "client_order_id": "c", "quantity": "0.2"}, ts_ns=2)
        recovered = StateReconciler(journal).replay(open_exchange_client_ids=["c"])["p"]
        assert recovered.children[0].state == "CANCEL_REQUIRED"
        assert recovered.can_resume is False


def test_absence_from_open_orders_is_unknown_not_assumed_filled_or_cancelled(tmp_path):
    with EventJournal(tmp_path / "events.sqlite") as journal:
        journal.append("parent-p", "PARENT_CREATED", {"parent_id": "p", "quantity": "0.2"}, ts_ns=1)
        journal.append("dispatch-c", "CHILD_DISPATCHED", {"parent_id": "p", "client_order_id": "c", "quantity": "0.2"}, ts_ns=2)
        recovered = StateReconciler(journal).replay(open_exchange_client_ids=[])["p"]
        assert recovered.children[0].state == "UNKNOWN"
        assert recovered.filled_quantity == 0
        assert recovered.remaining_size == D("0.2")
        assert recovered.can_resume is False


def test_replay_fails_closed_when_hash_chain_is_corrupt(tmp_path):
    with EventJournal(tmp_path / "events.sqlite") as journal:
        journal.append("p", "PARENT_CREATED", {"parent_id": "p", "quantity": "1"}, ts_ns=1)
        journal.db.execute("UPDATE events SET payload_json=? WHERE event_id='p'", ('{"parent_id":"p","quantity":"9"}',))
        journal.db.commit()
        with pytest.raises(RuntimeError, match="journal integrity failure"):
            StateReconciler(journal).replay()


def _sigkill_child(db_path: str, ready_path: str, partial: bool) -> None:
    with EventJournal(db_path) as journal:
        journal.append("parent-kill", "PARENT_CREATED", {"parent_id": "p-kill", "quantity": "1"}, ts_ns=1)
        journal.append("dispatch-child-1", "CHILD_DISPATCHED",
                       {"parent_id": "p-kill", "client_order_id": "child-1", "quantity": "0.4"}, ts_ns=2)
        if partial:
            journal.append("ack-child-1", "CHILD_ACKNOWLEDGED",
                           {"parent_id": "p-kill", "client_order_id": "child-1"}, ts_ns=3)
            journal.append("fill-child-1", "CHILD_PARTIAL_FILL",
                           {"parent_id": "p-kill", "client_order_id": "child-1", "fill_quantity": "0.15"}, ts_ns=4)
            journal.append("dispatch-child-2", "CHILD_DISPATCHED",
                           {"parent_id": "p-kill", "client_order_id": "child-2", "quantity": "0.2"}, ts_ns=5)
        with open(ready_path, "w", encoding="utf-8") as marker:
            marker.write("ready")
            marker.flush()
            os.fsync(marker.fileno())
        while True:
            time.sleep(10)


def _run_kill_recovery(tmp_path, partial: bool):
    db_path = str(tmp_path / ("partial.sqlite" if partial else "dispatch.sqlite"))
    ready_path = str(tmp_path / ("ready-partial" if partial else "ready-dispatch"))
    script = (
        "import sys; sys.path.insert(0, " + repr(os.getcwd()) + "); "
        "from recovery.test_state_reconciler import _sigkill_child; "
        "_sigkill_child(sys.argv[1],sys.argv[2],sys.argv[3]=='1')"
    )
    proc = subprocess.Popen([sys.executable, "-c", script, db_path, ready_path, "1" if partial else "0"],
                            cwd=os.getcwd(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not os.path.exists(ready_path):
            if proc.poll() is not None:
                raise AssertionError(f"child exited early with {proc.returncode}")
            time.sleep(0.01)
        assert os.path.exists(ready_path), "child did not reach durable-dispatch crash point"
        proc.kill()  # SIGKILL: intentional process-crash test at the durable dispatch boundary.
        proc.wait(timeout=5)
        assert proc.returncode == -9
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)
    with EventJournal(db_path) as journal:
        assert journal.verify()["valid"] is True
        events = journal.replay()
        assert sum(e["event_type"] == "CHILD_DISPATCHED" for e in events) == (2 if partial else 1)
        if partial:
            assert not any(e["event_type"] == "CHILD_ACKNOWLEDGED" and e["payload"].get("client_order_id") == "child-2" for e in events)
        else:
            assert not any(e["event_type"] == "CHILD_ACKNOWLEDGED" for e in events)
        recovered = StateReconciler(journal).replay()["p-kill"]
        expected_filled = D("0.15") if partial else D("0")
        assert recovered.filled_quantity == expected_filled
        assert recovered.remaining_size == D("1") - expected_filled
        assert recovered.can_resume is False
        assert any(c.reconciliation_required for c in recovered.children)


def test_sigkill_between_durable_dispatch_and_ack_recovers_exact_state(tmp_path):
    _run_kill_recovery(tmp_path, partial=False)


def test_sigkill_after_partial_fill_preserves_exact_parent_remaining_size(tmp_path):
    _run_kill_recovery(tmp_path, partial=True)
