"""Fail-closed production safety checks for short-horizon BTC execution.

Pure validation only: no exchange calls and no order submission.
"""
from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class ProductionLimits:
    max_market_age_seconds: float = 2.0
    max_spread_bps: float = 8.0
    max_slippage_bps: float = 8.0
    max_daily_loss_usd: float = 0.35
    max_consecutive_losses: int = 3
    max_positions: int = 1

    def __post_init__(self):
        values = (
            self.max_market_age_seconds, self.max_spread_bps,
            self.max_slippage_bps, self.max_daily_loss_usd,
        )
        if any(not math.isfinite(x) or x <= 0 for x in values):
            raise ValueError("market, spread, slippage and daily-loss limits must be finite and positive")
        if not isinstance(self.max_consecutive_losses, int) or self.max_consecutive_losses < 1:
            raise ValueError("max_consecutive_losses must be a positive integer")
        if not isinstance(self.max_positions, int) or self.max_positions < 1:
            raise ValueError("max_positions must be a positive integer")


@dataclass(frozen=True)
class MarketSnapshot:
    age_seconds: float
    spread_bps: float
    estimated_slippage_bps: float


@dataclass(frozen=True)
class AccountState:
    daily_loss_usd: float
    consecutive_losses: int
    open_positions: int
    kill_switch: bool = False


def validate_market(snapshot: MarketSnapshot, limits: ProductionLimits = ProductionLimits()):
    values = (snapshot.age_seconds, snapshot.spread_bps, snapshot.estimated_slippage_bps)
    if any(not math.isfinite(x) for x in values):
        return False, "NON_FINITE_MARKET_INPUT"
    if snapshot.age_seconds < 0 or snapshot.age_seconds > limits.max_market_age_seconds:
        return False, "STALE_MARKET_DATA"
    if snapshot.spread_bps < 0 or snapshot.spread_bps > limits.max_spread_bps:
        return False, "SPREAD_TOO_HIGH"
    if snapshot.estimated_slippage_bps < 0 or snapshot.estimated_slippage_bps > limits.max_slippage_bps:
        return False, "SLIPPAGE_TOO_HIGH"
    return True, "MARKET_OK"


def validate_account(account: AccountState, limits: ProductionLimits = ProductionLimits()):
    if not math.isfinite(account.daily_loss_usd):
        return False, "NON_FINITE_DAILY_LOSS"
    if not isinstance(account.consecutive_losses, int) or not isinstance(account.open_positions, int):
        return False, "INVALID_ACCOUNT_COUNTER"
    if account.kill_switch:
        return False, "KILL_SWITCH"
    if account.daily_loss_usd < 0:
        return False, "INVALID_DAILY_LOSS"
    if account.daily_loss_usd >= limits.max_daily_loss_usd:
        return False, "DAILY_LOSS_LIMIT"
    if account.consecutive_losses < 0:
        return False, "INVALID_CONSECUTIVE_LOSSES"
    if account.consecutive_losses >= limits.max_consecutive_losses:
        return False, "CONSECUTIVE_LOSS_LIMIT"
    if account.open_positions < 0 or account.open_positions >= limits.max_positions:
        return False, "POSITION_LIMIT"
    return True, "ACCOUNT_OK"


def validate_production(snapshot: MarketSnapshot, account: AccountState,
                        limits: ProductionLimits = ProductionLimits()):
    ok, reason = validate_market(snapshot, limits)
    if not ok:
        return False, reason
    ok, reason = validate_account(account, limits)
    if not ok:
        return False, reason
    return True, "PRODUCTION_SAFETY_OK"
