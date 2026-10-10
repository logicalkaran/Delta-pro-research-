"""Controller-level failure-mode tests: no signal evaluation on bad account state."""
from types import SimpleNamespace

from execution import live_perpetual_controller as controller


class FakeAdapter:
    def __init__(self, *, observed_at_ms, complete=True, missing_fields=()):
        self.state = SimpleNamespace(observed_at_ms=observed_at_ms, complete=complete,
            missing_fields=missing_fields, available_balance=1000.0, equity=1000.0,
            maintenance_margin=10.0)

    def account_state(self):
        return self.state


def test_controller_rejects_stale_account_before_signal(monkeypatch):
    monkeypatch.setattr(controller, "_load_state", lambda: {})
    monkeypatch.setattr(controller, "signal", lambda _: (_ for _ in ()).throw(
        AssertionError("signal must not be evaluated with stale account state")))
    result = controller.preflight(1.0, state_adapter=FakeAdapter(observed_at_ms=985_000),
                                  now_ms=1_000_000)
    assert result["reason"] == "STALE_DATA_REJECTION"
    assert result["signal"] is None
    assert result["order_submission"] == "DISABLED"


def test_controller_rejects_missing_margin_before_signal(monkeypatch):
    monkeypatch.setattr(controller, "_load_state", lambda: {})
    monkeypatch.setattr(controller, "signal", lambda _: (_ for _ in ()).throw(
        AssertionError("signal must not be evaluated without margin data")))
    adapter = FakeAdapter(observed_at_ms=1_000_000, complete=False,
                          missing_fields=("maintenance_margin",))
    result = controller.preflight(1.0, state_adapter=adapter, now_ms=1_000_000)
    assert result["reason"] == "MISSING_ACCOUNT_FIELDS:maintenance_margin"
    assert result["signal"] is None
    assert result["order_submission"] == "DISABLED"
