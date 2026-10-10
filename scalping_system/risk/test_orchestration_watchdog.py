import pytest

from risk.orchestration_watchdog import (
    WatchdogState, WatchdogTelemetry, evaluate_watchdog,
)


def healthy(**overrides):
    values = dict(
        websocket_latency_ms=80.0,
        seconds_since_last_heartbeat=1.0,
        market_data_age_seconds=0.2,
        process_memory_mb=120.0,
        heartbeat_received=True,
        supervisor_alive=True,
    )
    values.update(overrides)
    return WatchdogTelemetry(**values)


def test_healthy_telemetry_is_normal():
    result = evaluate_watchdog(healthy())
    assert result.state == WatchdogState.NORMAL
    assert not result.halt_new_signals
    assert not result.cancel_open_orders_via_rest


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"websocket_latency_ms": 501.0}, "WEBSOCKET_LATENCY_LIMIT"),
        ({"seconds_since_last_heartbeat": 10.1}, "HEARTBEAT_AGE_LIMIT"),
        ({"market_data_age_seconds": 2.1}, "MARKET_DATA_STALE"),
        ({"process_memory_mb": 501.0}, "MEMORY_LIMIT"),
        ({"heartbeat_received": False}, "WEBSOCKET_HEARTBEAT_MISSING"),
        ({"supervisor_alive": False}, "SUPERVISOR_NOT_ALIVE"),
    ],
)
def test_threshold_breach_requires_emergency_response(overrides, reason):
    result = evaluate_watchdog(healthy(**overrides))
    assert result.state == WatchdogState.EMERGENCY_REDUCE_ONLY
    assert reason in result.reasons
    assert result.halt_new_signals
    assert result.require_rest_reconciliation
    assert result.cancel_open_orders_via_rest
    assert result.permit_only_risk_reduction
    assert result.manual_reset_required


def test_non_finite_telemetry_fails_closed():
    result = evaluate_watchdog(healthy(websocket_latency_ms=float("nan")))
    assert result.state == WatchdogState.EMERGENCY_REDUCE_ONLY
    assert "NON_FINITE_WATCHDOG_TELEMETRY" in result.reasons


def test_invalid_watchdog_configuration_rejected():
    with pytest.raises(ValueError):
        evaluate_watchdog(healthy(), max_memory_mb=0)
