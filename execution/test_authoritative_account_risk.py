"""Adversarial tests for authoritative account-state risk checks."""
from dataclasses import dataclass
from types import SimpleNamespace

from execution.authoritative_account_risk import (
    AuthoritativeStateError, _anchors, evaluate_authoritative_intent,
)


@dataclass
class FakeState:
    available_balance: float | None = 900.0
    equity: float | None = 1000.0
    maintenance_margin: float | None = 10.0
    complete: bool = True
    missing_fields: tuple[str, ...] = ()
    observed_at_ms: int = 1_000_000


class FakeAdapter:
    def __init__(self, state=None, positions=None):
        self.state = state or FakeState()
        self.positions = positions if positions is not None else {
            "success": True, "result": [{"product_symbol": "BTCUSD", "signed_position_btc": 0.0}]
        }

    def account_state(self):
        return self.state

    def get_positions(self):
        return self.positions


class FakeJournal:
    def replay(self):
        return [
            {"seq": 1, "event_type": "DAILY_EQUITY_ANCHOR", "payload": {"equity": 1000.0, "observed_at_ms": 1_000_000}},
            {"seq": 2, "event_type": "WEEKLY_EQUITY_ANCHOR", "payload": {"equity": 1000.0, "observed_at_ms": 1_000_000}},
            {"seq": 3, "event_type": "PEAK_EQUITY_ANCHOR", "payload": {"equity": 1000.0, "observed_at_ms": 1_000_000}},
        ]


def run(adapter, qty=0.001, now=1_000_000):
    return evaluate_authoritative_intent(adapter=adapter, journal=FakeJournal(),
        symbol="BTCUSD", mark_price=60_000.0, proposed_signed_quantity_btc=qty,
        now_ms=now)


def test_rejects_stale_account_state():
    state = FakeState(observed_at_ms=985_000)
    result = run(FakeAdapter(state), now=1_000_000)
    assert result.verdict == "REJECTED"
    assert result.reason == "STALE_DATA_REJECTION"
    assert result.approved_signed_quantity_btc == 0.0


def test_rejects_missing_margin_data():
    state = FakeState(maintenance_margin=None, complete=False,
                      missing_fields=("maintenance_margin",))
    result = run(FakeAdapter(state))
    assert result.verdict == "REJECTED"
    assert "maintenance_margin" in result.reason


def test_prevents_sideloading_risk():
    adapter = FakeAdapter(positions={"success": True, "result": [
        {"product_symbol": "BTCUSD", "signed_position_btc": 0.5}
    ]})
    result = run(adapter, qty=1.0)
    assert result.current_position_btc == 0.5
    assert result.post_trade_exposure_btc == 1.5
    assert result.verdict in {"SCALED", "REJECTED"}
    assert result.approved_signed_quantity_btc < 1.0


def test_rejects_unknown_contract_to_btc_conversion():
    adapter = FakeAdapter(positions={"success": True, "result": [
        {"product_symbol": "BTCUSD", "size": 1}
    ]})
    result = run(adapter)
    assert result.verdict == "REJECTED"
    assert result.reason == "POSITION_BTC_DENOMINATION_UNVERIFIED"


def test_rejects_missing_equity_anchors():
    class EmptyJournal:
        def replay(self):
            return []
    result = evaluate_authoritative_intent(adapter=FakeAdapter(), journal=EmptyJournal(),
        symbol="BTCUSD", mark_price=60_000, proposed_signed_quantity_btc=0.001,
        now_ms=1_000_000)
    assert result.verdict == "REJECTED"
    assert result.reason.startswith("MISSING_DRAWDOWN_ANCHORS")


def test_hourly_equity_samples_derive_utc_day_week_and_historical_peak():
    import time

    now = int(time.time() * 1000)
    prior_week = now - 8 * 24 * 60 * 60 * 1000
    rows = [
        {"event_type": "AUTHORITATIVE_EQUITY_ANCHOR",
         "payload": {"equity": 1200.0, "observed_at_ms": prior_week}},
        {"event_type": "AUTHORITATIVE_EQUITY_ANCHOR",
         "payload": {"equity": 1000.0, "observed_at_ms": now - 3000}},
        {"event_type": "AUTHORITATIVE_EQUITY_ANCHOR",
         "payload": {"equity": 990.0, "observed_at_ms": now - 2000}},
        {"event_type": "AUTHORITATIVE_EQUITY_ANCHOR",
         "payload": {"equity": 1050.0, "observed_at_ms": now - 1000}},
    ]

    class Journal:
        def replay(self):
            return rows

    assert _anchors(Journal(), now) == (1000.0, 1000.0, 1200.0)


def test_old_equity_samples_cannot_substitute_for_current_day_or_week():
    import time

    now = int(time.time() * 1000)
    old_timestamp = now - 8 * 24 * 60 * 60 * 1000

    class Journal:
        def replay(self):
            return [{"event_type": "AUTHORITATIVE_EQUITY_ANCHOR",
                     "payload": {"equity": 1000.0, "observed_at_ms": old_timestamp}}]

    try:
        _anchors(Journal(), now)
    except AuthoritativeStateError as exc:
        assert str(exc).startswith("MISSING_DRAWDOWN_ANCHORS:day,week")
    else:
        raise AssertionError("stale period samples must not create current anchors")
