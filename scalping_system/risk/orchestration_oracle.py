"""Pure, fail-closed orchestration risk oracle.

This module implements the risk logic described in the Orchestration Tier PDF.
It is deliberately side-effect-free: no exchange calls, filesystem writes, or
order submission. Live wiring is prohibited until authoritative account equity,
drawdown anchors, position and maintenance-margin inputs are supplied.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math


class Verdict(str, Enum):
    APPROVED = "APPROVED"
    SCALED = "SCALED"
    REJECTED = "REJECTED"
    REDUCE_ONLY = "REDUCE_ONLY"


@dataclass(frozen=True)
class RiskLimits:
    max_net_exposure_btc: float = 0.001
    adverse_shock_fraction: float = 0.05
    min_stress_headroom_fraction: float = 0.20
    max_daily_drawdown_fraction: float = 0.02
    max_weekly_drawdown_fraction: float = 0.05
    max_peak_to_trough_drawdown_fraction: float = 0.10
    max_scale_iterations: int = 100

    def __post_init__(self) -> None:
        if not math.isfinite(self.max_net_exposure_btc) or self.max_net_exposure_btc <= 0:
            raise ValueError("max_net_exposure_btc must be finite and positive")
        if not 0 < self.adverse_shock_fraction < 1:
            raise ValueError("adverse_shock_fraction must be between 0 and 1")
        if not 0 <= self.min_stress_headroom_fraction < 1:
            raise ValueError("min_stress_headroom_fraction must be in [0, 1)")
        for value in (
            self.max_daily_drawdown_fraction,
            self.max_weekly_drawdown_fraction,
            self.max_peak_to_trough_drawdown_fraction,
        ):
            if not math.isfinite(value) or not 0 < value < 1:
                raise ValueError("drawdown limits must be finite fractions between 0 and 1")
        if not isinstance(self.max_scale_iterations, int) or self.max_scale_iterations < 1:
            raise ValueError("max_scale_iterations must be a positive integer")


@dataclass(frozen=True)
class PortfolioSnapshot:
    mark_price: float
    account_equity: float
    current_position_btc: float
    maintenance_margin_rate: float
    day_start_equity: float
    week_start_equity: float
    peak_equity: float
    market_data_age_seconds: float = 0.0
    websocket_latency_ms: float = 0.0
    memory_mb: float = 0.0
    kill_switch: bool = False


@dataclass(frozen=True)
class OrderIntent:
    # Signed BTC quantity: positive buys/increases long exposure; negative sells.
    signed_quantity_btc: float
    reason: str = "NEW_ENTRY"


@dataclass(frozen=True)
class RiskDecision:
    verdict: Verdict
    approved_signed_quantity_btc: float
    reason_codes: tuple[str, ...]
    net_exposure_btc: float | None = None
    stress_equity: float | None = None
    stress_maintenance_margin: float | None = None
    stress_headroom_fraction: float | None = None
    daily_drawdown_fraction: float | None = None
    weekly_drawdown_fraction: float | None = None
    peak_drawdown_fraction: float | None = None


def _finite_positive(value: float) -> bool:
    return math.isfinite(value) and value > 0


def _validate_snapshot(s: PortfolioSnapshot, limits: RiskLimits) -> list[str]:
    reasons: list[str] = []
    if not _finite_positive(s.mark_price):
        reasons.append("INVALID_MARK_PRICE")
    if not _finite_positive(s.account_equity):
        reasons.append("INVALID_ACCOUNT_EQUITY")
    if not all(math.isfinite(x) for x in (
        s.current_position_btc, s.maintenance_margin_rate, s.day_start_equity,
        s.week_start_equity, s.peak_equity, s.market_data_age_seconds,
        s.websocket_latency_ms, s.memory_mb,
    )):
        reasons.append("NON_FINITE_RISK_INPUT")
        return reasons
    if not 0 < s.maintenance_margin_rate < 1:
        reasons.append("INVALID_MAINTENANCE_MARGIN_RATE")
    if not _finite_positive(s.day_start_equity):
        reasons.append("INVALID_DAY_START_EQUITY")
    if not _finite_positive(s.week_start_equity):
        reasons.append("INVALID_WEEK_START_EQUITY")
    if not _finite_positive(s.peak_equity):
        reasons.append("INVALID_PEAK_EQUITY")
    if s.market_data_age_seconds < 0 or s.market_data_age_seconds > 2.0:
        reasons.append("STALE_MARKET_DATA")
    if s.websocket_latency_ms < 0 or s.websocket_latency_ms > 500.0:
        reasons.append("NETWORK_WATCHDOG_TRIPPED")
    if s.memory_mb < 0 or s.memory_mb > 500.0:
        reasons.append("MEMORY_WATCHDOG_TRIPPED")
    if s.kill_switch:
        reasons.append("KILL_SWITCH_ACTIVE")
    return reasons


def _drawdowns(s: PortfolioSnapshot) -> tuple[float, float, float]:
    return (
        max(0.0, (s.day_start_equity - s.account_equity) / s.day_start_equity),
        max(0.0, (s.week_start_equity - s.account_equity) / s.week_start_equity),
        max(0.0, (s.peak_equity - s.account_equity) / s.peak_equity),
    )


def _stress(s: PortfolioSnapshot, proposed_signed_qty: float, limits: RiskLimits):
    net = s.current_position_btc + proposed_signed_qty
    shock = limits.adverse_shock_fraction
    # Evaluate both shock directions and retain the worse outcome. This also
    # handles a proposed order that offsets an existing position.
    down_mark = s.mark_price * (1.0 - shock)
    up_mark = s.mark_price * (1.0 + shock)
    down_equity = s.account_equity + net * (down_mark - s.mark_price)
    up_equity = s.account_equity + net * (up_mark - s.mark_price)
    if down_equity <= up_equity:
        stress_mark, stress_equity = down_mark, down_equity
    else:
        stress_mark, stress_equity = up_mark, up_equity
    maintenance = abs(net) * stress_mark * s.maintenance_margin_rate
    headroom = (stress_equity - maintenance) / stress_equity if stress_equity > 0 else -math.inf
    return net, stress_equity, maintenance, headroom


def evaluate(
    snapshot: PortfolioSnapshot,
    intent: OrderIntent,
    limits: RiskLimits = RiskLimits(),
) -> RiskDecision:
    """Return APPROVED, SCALED, REDUCE_ONLY or REJECTED for a proposed entry."""
    if not math.isfinite(intent.signed_quantity_btc) or intent.signed_quantity_btc == 0:
        return RiskDecision(Verdict.REJECTED, 0.0, ("INVALID_ORDER_QUANTITY",))

    invalid = _validate_snapshot(snapshot, limits)
    if invalid:
        return RiskDecision(Verdict.REJECTED, 0.0, tuple(invalid))

    daily_dd, weekly_dd, peak_dd = _drawdowns(snapshot)
    fuse_reasons = []
    if daily_dd >= limits.max_daily_drawdown_fraction:
        fuse_reasons.append("DAILY_DRAWDOWN_FUSE")
    if weekly_dd >= limits.max_weekly_drawdown_fraction:
        fuse_reasons.append("WEEKLY_DRAWDOWN_FUSE")
    if peak_dd >= limits.max_peak_to_trough_drawdown_fraction:
        fuse_reasons.append("PEAK_DRAWDOWN_FUSE")

    current = snapshot.current_position_btc
    proposed = intent.signed_quantity_btc
    final_net = current + proposed
    # Explicitly allow only an order that reduces absolute exposure without
    # crossing through flat; the caller must route it through a reduce-only API.
    if abs(final_net) < abs(current) and (current == 0 or final_net == 0 or current * final_net >= 0):
        return RiskDecision(
            Verdict.REDUCE_ONLY, proposed, ("RISK_REDUCING_ORDER_ONLY",),
            net_exposure_btc=final_net, daily_drawdown_fraction=daily_dd,
            weekly_drawdown_fraction=weekly_dd, peak_drawdown_fraction=peak_dd,
        )

    if fuse_reasons:
        return RiskDecision(
            Verdict.REJECTED, 0.0, tuple(fuse_reasons),
            net_exposure_btc=final_net, daily_drawdown_fraction=daily_dd,
            weekly_drawdown_fraction=weekly_dd, peak_drawdown_fraction=peak_dd,
        )

    net, stress_equity, maintenance, headroom = _stress(snapshot, proposed, limits)
    base = dict(
        net_exposure_btc=net, stress_equity=stress_equity,
        stress_maintenance_margin=maintenance, stress_headroom_fraction=headroom,
        daily_drawdown_fraction=daily_dd, weekly_drawdown_fraction=weekly_dd,
        peak_drawdown_fraction=peak_dd,
    )
    if abs(net) <= limits.max_net_exposure_btc and headroom >= limits.min_stress_headroom_fraction:
        return RiskDecision(Verdict.APPROVED, proposed, ("RISK_ORACLE_APPROVED",), **base)

    # Find the largest admissible order fraction instead of using a coarse grid.
    # A new entry is not scaled if the existing portfolio already breaches limits.
    def candidate_state(fraction: float):
        qty = proposed * fraction
        n, equity, mm, margin_headroom = _stress(snapshot, qty, limits)
        ok = abs(n) <= limits.max_net_exposure_btc and margin_headroom >= limits.min_stress_headroom_fraction
        return ok, qty, n, equity, mm, margin_headroom

    zero_ok, *_ = candidate_state(0.0)
    if not zero_ok:
        return RiskDecision(Verdict.REJECTED, 0.0, ("EXISTING_EXPOSURE_OR_STRESS_MARGIN_LIMIT",), **base)
    low, high = 0.0, 1.0
    best = candidate_state(0.0)
    for _ in range(limits.max_scale_iterations):
        mid = (low + high) / 2.0
        state = candidate_state(mid)
        if state[0]:
            low = mid
            best = state
        else:
            high = mid
    _, qty, candidate_net, candidate_equity, candidate_mm, candidate_headroom = best
    if qty <= 0.0:
        return RiskDecision(Verdict.REJECTED, 0.0, ("EXPOSURE_OR_STRESS_MARGIN_LIMIT",), **base)
    return RiskDecision(
        Verdict.SCALED, qty, ("ORDER_SCALED_TO_RISK_LIMITS",),
        net_exposure_btc=candidate_net, stress_equity=candidate_equity,
        stress_maintenance_margin=candidate_mm,
        stress_headroom_fraction=candidate_headroom,
        daily_drawdown_fraction=daily_dd, weekly_drawdown_fraction=weekly_dd,
        peak_drawdown_fraction=peak_dd,
    )
