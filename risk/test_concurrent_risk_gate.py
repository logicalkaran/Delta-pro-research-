import concurrent.futures
import threading
import pytest

from risk.concurrent_risk_gate import ConcurrentRiskGate
from risk.orchestration_oracle import OrderIntent, PortfolioSnapshot, RiskLimits, Verdict


def snapshot(**overrides):
    values = dict(
        mark_price=65000.0, account_equity=1000.0, current_position_btc=0.0,
        maintenance_margin_rate=0.005, day_start_equity=1000.0,
        week_start_equity=1000.0, peak_equity=1000.0,
        market_data_age_seconds=0.1, websocket_latency_ms=50.0, memory_mb=100.0,
        kill_switch=False,
    )
    values.update(overrides)
    return PortfolioSnapshot(**values)


def test_concurrent_reservations_include_pending_intents_before_risk_decision():
    gate = ConcurrentRiskGate(RiskLimits(max_net_exposure_btc=0.001))
    barrier = threading.Barrier(8)

    def submit(i):
        barrier.wait()
        return gate.reserve(f"intent-{i}", snapshot(), OrderIntent(0.0007))

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(submit, range(8)))
    assert sum(r.approved_signed_quantity_btc for r in results) <= 0.001 + 1e-9
    assert sum(r.approved_signed_quantity_btc > 0 for r in results) >= 1


def test_duplicate_intent_id_cannot_be_reserved_twice():
    gate = ConcurrentRiskGate()
    assert gate.reserve("same", snapshot(), OrderIntent(0.0005)).verdict == Verdict.APPROVED
    second = gate.reserve("same", snapshot(), OrderIntent(0.0005))
    assert second.verdict == Verdict.REJECTED
    assert "DUPLICATE_INTENT_ID" in second.reason_codes


def test_unknown_reservation_cannot_be_released_silently():
    gate = ConcurrentRiskGate()
    gate.reserve("unknown-outcome", snapshot(), OrderIntent(0.0005))
    with pytest.raises(ValueError):
        gate.resolve_cancelled("unknown-outcome", cancellation_confirmed=False)
    assert "unknown-outcome" in gate.unresolved_ids()


def test_filled_reservation_requires_authoritative_snapshot_update():
    gate = ConcurrentRiskGate()
    gate.reserve("filled", snapshot(), OrderIntent(0.0005))
    with pytest.raises(ValueError):
        gate.resolve_filled("filled", filled_signed_quantity_btc=0.0005,
                            authoritative_snapshot_updated=False, order_terminal_confirmed=False)
    assert "filled" in gate.unresolved_ids()
    gate.resolve_filled("filled", filled_signed_quantity_btc=0.0005,
                        authoritative_snapshot_updated=True, order_terminal_confirmed=True)
    assert "filled" not in gate.unresolved_ids()


def test_canceled_reservation_released_only_after_confirmed_cancel():
    gate = ConcurrentRiskGate()
    gate.reserve("cancelled", snapshot(), OrderIntent(0.0005))
    with pytest.raises(ValueError):
        gate.resolve_cancelled("cancelled", cancellation_confirmed=False)
    gate.resolve_cancelled("cancelled", cancellation_confirmed=True)
    assert not gate.unresolved_ids()


def test_concurrent_opposite_intent_is_blocked_while_first_is_unresolved():
    gate = ConcurrentRiskGate(RiskLimits(max_net_exposure_btc=0.001))
    first = gate.reserve("long", snapshot(), OrderIntent(0.0005))
    second = gate.reserve("short", snapshot(), OrderIntent(-0.0005))
    assert first.verdict == Verdict.APPROVED
    assert second.verdict == Verdict.REJECTED
    assert "UNRESOLVED_INTENT_RESERVATION" in second.reason_codes
