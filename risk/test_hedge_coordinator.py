import json
import sqlite3

import pytest

from storage.event_journal import EventJournal
from risk.hedge_coordinator import (
    PairState, PairTelemetry, evaluate_pair, expected_funding_pnl_usd,
)


def test_event_journal_append_verify_replay(tmp_path):
    path = tmp_path / "events.sqlite"
    with EventJournal(path) as journal:
        one = journal.append("e1", "ORDER_INTENT", {"side": "buy", "qty": 1}, ts_ns=10)
        two = journal.append("e2", "ORDER_ACK", {"order_id": "abc"}, ts_ns=20)
        assert one["seq"] == 1 and two["seq"] == 2
        assert journal.verify()["valid"]
        assert [x["event_id"] for x in journal.replay(after_seq=1)] == ["e2"]


def test_event_journal_rejects_duplicate_id(tmp_path):
    with EventJournal(tmp_path / "events.sqlite") as journal:
        journal.append("same", "A", {}, ts_ns=1)
        with pytest.raises(ValueError):
            journal.append("same", "B", {}, ts_ns=2)


def test_event_journal_detects_mutated_payload(tmp_path):
    path = tmp_path / "events.sqlite"
    with EventJournal(path) as journal:
        journal.append("e1", "A", {"value": 1}, ts_ns=1)
        journal.append("e2", "B", {"value": 2}, ts_ns=2)
    db = sqlite3.connect(path)
    db.execute("UPDATE events SET payload_json=? WHERE event_id='e1'", ('{"value":9}',))
    db.commit()
    db.close()
    with EventJournal(path) as journal:
        result = journal.verify()
        assert not result["valid"]
        assert result["reason"] == "EVENT_HASH_MISMATCH"


def pair(**overrides):
    values = dict(
        primary_filled_btc=0.001, hedge_filled_btc=0.001,
        primary_requested_btc=0.001, hedge_requested_btc=0.001,
        primary_age_seconds=0.1, hedge_age_seconds=0.1,
    )
    values.update(overrides)
    return PairTelemetry(**values)


def test_pair_balanced():
    result = evaluate_pair(pair())
    assert result.state == PairState.BALANCED
    assert abs(result.net_delta_btc) < 1e-12
    assert not result.halt_new_entries


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"hedge_filled_btc": 0.0001}, "UNHEDGED_DELTA_LIMIT"),
        ({"primary_filled_btc": 0.0005, "hedge_filled_btc": 0.0005, "hedge_age_seconds": 1.5}, "PAIR_LEG_TIMEOUT"),
        ({"hedge_filled_btc": 0.0005}, "PAIR_FILL_MISMATCH"),
    ],
)
def test_orphan_leg_breaker(overrides, reason):
    result = evaluate_pair(pair(**overrides))
    assert result.state == PairState.EMERGENCY_REDUCE_ONLY
    assert reason in result.reasons
    assert result.halt_new_entries
    assert result.reconcile_both_venues
    assert result.reduce_orphaned_leg
    assert result.require_manual_reset


def test_pair_partial_fills_halt_new_entries_until_completed():
    result = evaluate_pair(pair(primary_filled_btc=0.0005, hedge_filled_btc=0.0005))
    assert result.state == PairState.HEDGE_PENDING
    assert result.halt_new_entries


def test_funding_estimate_positive_only_after_costs():
    result = expected_funding_pnl_usd(
        spot_notional_usd=1000, perpetual_notional_usd=1000,
        funding_rate=0.001, funding_receiving_side="short",
        estimated_total_cost_usd=0.2,
    )
    assert result["gross_funding_estimate_usd"] == pytest.approx(1.0)
    assert result["net_estimate_usd"] == pytest.approx(0.8)
    assert result["estimated_positive_after_costs"]


def test_funding_estimate_can_be_negative_after_costs():
    result = expected_funding_pnl_usd(
        spot_notional_usd=1000, perpetual_notional_usd=1000,
        funding_rate=0.0001, funding_receiving_side="short",
        estimated_total_cost_usd=0.5,
    )
    assert result["net_estimate_usd"] == pytest.approx(-0.4)
    assert not result["estimated_positive_after_costs"]


def test_completed_balanced_pair_does_not_timeout_just_because_old():
    result = evaluate_pair(pair(primary_age_seconds=30.0, hedge_age_seconds=30.0))
    assert result.state == PairState.BALANCED
    assert not result.require_manual_reset


def test_negative_funding_pays_long_receiver():
    result = expected_funding_pnl_usd(
        spot_notional_usd=1000, perpetual_notional_usd=1000,
        funding_rate=-0.001, funding_receiving_side="long",
        estimated_total_cost_usd=0.2,
    )
    assert result["gross_funding_estimate_usd"] == pytest.approx(1.0)
    assert result["net_estimate_usd"] == pytest.approx(0.8)


def test_event_journal_external_anchor_detects_tail_truncation(tmp_path):
    path = tmp_path / "events.sqlite"
    with EventJournal(path) as journal:
        journal.append("e1", "A", {"value": 1}, ts_ns=1)
        final = journal.append("e2", "B", {"value": 2}, ts_ns=2)
        anchor_hash = final["event_hash"]
        anchor_seq = final["seq"]
    db = sqlite3.connect(path)
    db.execute("DELETE FROM events WHERE event_id='e2'")
    db.commit()
    db.close()
    with EventJournal(path) as journal:
        assert journal.verify()["valid"]  # local chain alone cannot prove tail completeness
        anchored = journal.verify(expected_terminal_hash=anchor_hash, expected_last_seq=anchor_seq)
        assert not anchored["valid"]
        assert anchored["reason"] in {"TERMINAL_HASH_ANCHOR_MISMATCH", "TERMINAL_SEQUENCE_ANCHOR_MISMATCH"}
