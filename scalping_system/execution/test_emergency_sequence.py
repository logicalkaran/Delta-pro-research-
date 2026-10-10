from execution.emergency_sequence import run_emergency_sequence
from risk.orchestration_watchdog import WatchdogState, WatchdogTelemetry, evaluate_watchdog


class MockEmergencyAdapter:
    def __init__(self, response=None, fail_cancel=False):
        self.calls = []
        self.response = response or {"success": True, "confirmed": True}
        self.fail_cancel = fail_cancel
        self.events = []

    def halt_signal_ingestion(self):
        self.calls.append("halt_signals")

    def set_engine_state(self, state):
        self.calls.append("state:" + state)

    def cancel_all_open_limit_orders(self):
        self.calls.append("cancel_all")
        if self.fail_cancel:
            raise TimeoutError()
        return self.response

    def append_audit_event(self, event):
        self.calls.append("audit")
        self.events.append(event)


def healthy(**overrides):
    values = dict(
        websocket_latency_ms=50.0, seconds_since_last_heartbeat=1.0,
        market_data_age_seconds=0.1, process_memory_mb=100.0,
        heartbeat_received=True, supervisor_alive=True,
    )
    values.update(overrides)
    return WatchdogTelemetry(**values)


def test_latency_fuzz_trips_breaker_above_500ms():
    for latency in (500.01, 501, 1000, 10000):
        decision = evaluate_watchdog(healthy(websocket_latency_ms=latency))
        assert decision.state == WatchdogState.EMERGENCY_REDUCE_ONLY
        assert decision.halt_new_signals
        assert decision.manual_reset_required


def test_missing_heartbeat_trips_breaker():
    decision = evaluate_watchdog(healthy(heartbeat_received=False))
    assert decision.state == WatchdogState.EMERGENCY_REDUCE_ONLY
    assert "WEBSOCKET_HEARTBEAT_MISSING" in decision.reasons


def test_memory_pressure_trips_before_500mb_boundary():
    for memory in (499.9, 500.01, 520, 600):
        decision = evaluate_watchdog(healthy(process_memory_mb=memory))
        assert (decision.state == WatchdogState.NORMAL) == (memory <= 500.0)
        if memory > 500.0:
            assert decision.halt_new_signals
            assert "MEMORY_LIMIT" in decision.reasons


def test_emergency_sequence_order_and_confirmed_cancel():
    adapter = MockEmergencyAdapter()
    result = run_emergency_sequence(adapter, ("WEBSOCKET_LATENCY_LIMIT",))
    assert adapter.calls == [
        "halt_signals", "state:EMERGENCY_REDUCE_ONLY", "cancel_all", "audit"
    ]
    assert result.state == "EMERGENCY_REDUCE_ONLY"
    assert result.signal_ingestion_halted
    assert result.cancel_requested and result.cancel_confirmed
    assert adapter.events[0]["reasons"] == ["WEBSOCKET_LATENCY_LIMIT"]
    assert adapter.events[0]["state_persisted"] is True


def test_cancel_timeout_is_not_reported_as_success():
    adapter = MockEmergencyAdapter(fail_cancel=True)
    result = run_emergency_sequence(adapter, ("HEARTBEAT_AGE_LIMIT",))
    assert result.state == "EMERGENCY_REDUCE_ONLY"
    assert result.cancel_requested and not result.cancel_confirmed
    assert any(x.startswith("CANCEL_ALL_REQUEST_FAILED") for x in result.errors)


def test_unconfirmed_cancel_response_is_not_success():
    adapter = MockEmergencyAdapter(response={"success": True, "confirmed": False})
    result = run_emergency_sequence(adapter, ("MEMORY_LIMIT",))
    assert not result.cancel_confirmed
    assert "CANCEL_ALL_NOT_CONFIRMED" in result.errors


class StateFailureAdapter(MockEmergencyAdapter):
    def set_engine_state(self, state):
        self.calls.append("state:" + state)
        raise OSError("disk unavailable")


def test_result_distinguishes_requested_emergency_state_from_persisted_state():
    adapter = StateFailureAdapter()
    result = run_emergency_sequence(adapter, ("MEMORY_LIMIT",))
    assert result.state == "EMERGENCY_REDUCE_ONLY"  # intended state
    assert not result.state_persisted
    assert result.signal_ingestion_halted
    assert result.cancel_confirmed
    assert any(x.startswith("SET_EMERGENCY_STATE_FAILED") for x in result.errors)
