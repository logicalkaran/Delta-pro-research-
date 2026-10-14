import math
import pytest

from risk.orchestration_oracle import (
    OrderIntent, PortfolioSnapshot, RiskLimits, Verdict, evaluate,
)


def snapshot(**overrides):
    values = dict(
        mark_price=65000.0,
        account_equity=1000.0,
        current_position_btc=0.0,
        maintenance_margin_rate=0.005,
        day_start_equity=1000.0,
        week_start_equity=1000.0,
        peak_equity=1000.0,
        market_data_age_seconds=0.2,
        websocket_latency_ms=80.0,
        memory_mb=120.0,
        kill_switch=False,
    )
    values.update(overrides)
    return PortfolioSnapshot(**values)


def test_small_valid_entry_is_approved():
    result = evaluate(snapshot(), OrderIntent(0.001))
    assert result.verdict == Verdict.APPROVED
    assert result.approved_signed_quantity_btc == 0.001
    assert result.stress_headroom_fraction >= 0.20


def test_order_is_scaled_to_exposure_cap():
    result = evaluate(snapshot(), OrderIntent(0.002))
    assert result.verdict == Verdict.SCALED
    assert 0 < result.approved_signed_quantity_btc <= 0.001
    assert abs(result.net_exposure_btc) <= 0.001


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"market_data_age_seconds": 2.01}, "STALE_MARKET_DATA"),
        ({"websocket_latency_ms": 500.1}, "NETWORK_WATCHDOG_TRIPPED"),
        ({"memory_mb": 500.1}, "MEMORY_WATCHDOG_TRIPPED"),
        ({"kill_switch": True}, "KILL_SWITCH_ACTIVE"),
        ({"account_equity": float("nan")}, "INVALID_ACCOUNT_EQUITY"),
        ({"maintenance_margin_rate": 1.0}, "INVALID_MAINTENANCE_MARGIN_RATE"),
    ],
)
def test_invalid_or_unsafe_snapshot_fails_closed(overrides, reason):
    result = evaluate(snapshot(**overrides), OrderIntent(0.001))
    assert result.verdict == Verdict.REJECTED
    assert reason in result.reason_codes
    assert result.approved_signed_quantity_btc == 0


def test_daily_drawdown_fuse_blocks_new_entry():
    result = evaluate(
        snapshot(account_equity=979.0, day_start_equity=1000.0),
        OrderIntent(0.001),
    )
    assert result.verdict == Verdict.REJECTED
    assert "DAILY_DRAWDOWN_FUSE" in result.reason_codes


def test_weekly_and_peak_drawdown_fuses_are_independent():
    weekly = evaluate(
        snapshot(account_equity=940.0, week_start_equity=1000.0),
        OrderIntent(0.001),
    )
    peak = evaluate(
        snapshot(account_equity=890.0, peak_equity=1000.0),
        OrderIntent(0.001),
    )
    assert "WEEKLY_DRAWDOWN_FUSE" in weekly.reason_codes
    assert "PEAK_DRAWDOWN_FUSE" in peak.reason_codes


def test_reduce_only_intent_is_not_mistaken_for_new_risk():
    result = evaluate(
        snapshot(current_position_btc=0.001),
        OrderIntent(-0.0005, reason="REDUCE"),
    )
    assert result.verdict == Verdict.REDUCE_ONLY
    assert result.approved_signed_quantity_btc == -0.0005


def test_order_that_crosses_through_flat_is_not_reduce_only():
    result = evaluate(
        snapshot(current_position_btc=0.001),
        OrderIntent(-0.002),
    )
    assert result.verdict in {Verdict.APPROVED, Verdict.SCALED, Verdict.REJECTED}
    assert result.verdict != Verdict.REDUCE_ONLY


def test_bad_order_quantity_rejected():
    result = evaluate(snapshot(), OrderIntent(float("nan")))
    assert result.verdict == Verdict.REJECTED
    assert result.reason_codes == ("INVALID_ORDER_QUANTITY",)


def test_limits_reject_invalid_configuration():
    with pytest.raises(ValueError):
        RiskLimits(max_net_exposure_btc=0)
    with pytest.raises(ValueError):
        RiskLimits(adverse_shock_fraction=1.0)


def test_large_order_is_scaled_below_old_one_percent_grid():
    result = evaluate(snapshot(), OrderIntent(1.0))
    assert result.verdict == Verdict.SCALED
    assert 0 < result.approved_signed_quantity_btc <= 0.001
    assert result.approved_signed_quantity_btc < 0.01
    assert result.stress_headroom_fraction >= 0.20
