import math
import pytest

from risk.production_guard import (
    AccountState, MarketSnapshot, ProductionLimits,
    validate_market, validate_account, validate_production,
)


def market():
    return MarketSnapshot(age_seconds=0.5, spread_bps=2.0, estimated_slippage_bps=1.0)


def test_market_passes():
    assert validate_market(market())[0]


def test_stale_market_blocks():
    assert validate_market(MarketSnapshot(2.01, 2, 1))[1] == "STALE_MARKET_DATA"


def test_spread_blocks():
    assert validate_market(MarketSnapshot(.5, 8.01, 1))[1] == "SPREAD_TOO_HIGH"


def test_slippage_blocks():
    assert validate_market(MarketSnapshot(.5, 2, 8.01))[1] == "SLIPPAGE_TOO_HIGH"


def test_daily_loss_blocks():
    assert validate_account(AccountState(.35, 0, 0))[1] == "DAILY_LOSS_LIMIT"


def test_consecutive_losses_block():
    assert validate_account(AccountState(0, 3, 0))[1] == "CONSECUTIVE_LOSS_LIMIT"


def test_position_blocks():
    assert validate_account(AccountState(0, 0, 1))[1] == "POSITION_LIMIT"


def test_kill_switch_blocks():
    assert validate_account(AccountState(0, 0, 0, True))[1] == "KILL_SWITCH"


def test_production_passes():
    assert validate_production(market(), AccountState(0, 0, 0))[0]


def test_non_finite_market_inputs_fail_closed():
    for value in (math.nan, math.inf, -math.inf):
        ok, reason = validate_market(MarketSnapshot(value, 1.0, 1.0))
        assert not ok and reason == "NON_FINITE_MARKET_INPUT"
        ok, reason = validate_market(MarketSnapshot(0.5, value, 1.0))
        assert not ok and reason == "NON_FINITE_MARKET_INPUT"
        ok, reason = validate_market(MarketSnapshot(0.5, 1.0, value))
        assert not ok and reason == "NON_FINITE_MARKET_INPUT"


def test_non_finite_account_loss_fails_closed():
    for value in (math.nan, math.inf, -math.inf):
        ok, reason = validate_account(AccountState(value, 0, 0))
        assert not ok and reason == "NON_FINITE_DAILY_LOSS"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_market_age_seconds": math.nan},
        {"max_spread_bps": math.inf},
        {"max_slippage_bps": 0},
        {"max_daily_loss_usd": -1},
        {"max_consecutive_losses": 0},
        {"max_positions": 0},
    ],
)
def test_invalid_production_limits_rejected(kwargs):
    with pytest.raises(ValueError):
        ProductionLimits(**kwargs)


def test_non_integer_account_counters_fail_closed():
    ok, reason = validate_account(AccountState(0.0, 1.5, 0))
    assert not ok and reason == "INVALID_ACCOUNT_COUNTER"
    ok, reason = validate_account(AccountState(0.0, 0, 0.5))
    assert not ok and reason == "INVALID_ACCOUNT_COUNTER"
