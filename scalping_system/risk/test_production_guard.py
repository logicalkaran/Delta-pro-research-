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
