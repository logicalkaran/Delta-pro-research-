"""Cross-venue hedge accounting and orphan-leg breaker policy.

Pure policy only: this module does not call exchanges or submit orders. Amounts
must be normalized into BTC-equivalent delta by a trusted venue adapter.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math


class PairState(str, Enum):
    BALANCED = "BALANCED"
    HEDGE_PENDING = "HEDGE_PENDING"
    EMERGENCY_REDUCE_ONLY = "EMERGENCY_REDUCE_ONLY"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class PairTelemetry:
    primary_filled_btc: float
    hedge_filled_btc: float
    primary_requested_btc: float
    hedge_requested_btc: float
    primary_age_seconds: float
    hedge_age_seconds: float
    max_unhedged_btc: float = 0.0001
    max_leg_age_seconds: float = 1.0
    max_fill_mismatch_fraction: float = 0.05


@dataclass(frozen=True)
class PairDecision:
    state: PairState
    net_delta_btc: float
    hedge_ratio: float | None
    reasons: tuple[str, ...]
    halt_new_entries: bool
    reconcile_both_venues: bool
    reduce_orphaned_leg: bool
    require_manual_reset: bool


def evaluate_pair(t: PairTelemetry) -> PairDecision:
    values = (
        t.primary_filled_btc, t.hedge_filled_btc, t.primary_requested_btc,
        t.hedge_requested_btc, t.primary_age_seconds, t.hedge_age_seconds,
        t.max_unhedged_btc, t.max_leg_age_seconds, t.max_fill_mismatch_fraction,
    )
    if any(not math.isfinite(x) for x in values):
        return PairDecision(PairState.REJECTED, math.nan, None,
                            ("NON_FINITE_PAIR_TELEMETRY",), True, True, True, True)
    if (min(t.primary_filled_btc, t.hedge_filled_btc, t.primary_requested_btc,
            t.hedge_requested_btc, t.primary_age_seconds, t.hedge_age_seconds) < 0
            or t.max_unhedged_btc <= 0 or t.max_leg_age_seconds <= 0
            or not 0 <= t.max_fill_mismatch_fraction < 1):
        return PairDecision(PairState.REJECTED, 0.0, None,
                            ("INVALID_PAIR_TELEMETRY",), True, True, True, True)

    if t.primary_requested_btc == 0 or t.hedge_requested_btc == 0:
        return PairDecision(PairState.REJECTED, 0.0, None,
                            ("ZERO_REQUESTED_LEG",), True, True, True, True)

    net = t.primary_filled_btc - t.hedge_filled_btc
    larger = max(t.primary_filled_btc, t.hedge_filled_btc)
    mismatch = abs(t.primary_filled_btc - t.hedge_filled_btc) / larger if larger else 0.0
    ratio = (t.hedge_filled_btc / t.primary_filled_btc
             if t.primary_filled_btc else (1.0 if t.hedge_filled_btc == 0 else 0.0))
    primary_done = t.primary_filled_btc >= t.primary_requested_btc
    hedge_done = t.hedge_filled_btc >= t.hedge_requested_btc
    pending = not (primary_done and hedge_done)
    # Only unresolved legs can time out; age alone does not orphan a completed pair.
    stale_leg = pending and max(t.primary_age_seconds, t.hedge_age_seconds) > t.max_leg_age_seconds
    over_mismatch = mismatch > t.max_fill_mismatch_fraction
    over_delta = abs(net) > t.max_unhedged_btc

    if stale_leg or over_mismatch or over_delta:
        reasons = tuple(
            code for condition, code in (
                (stale_leg, "PAIR_LEG_TIMEOUT"),
                (over_mismatch, "PAIR_FILL_MISMATCH"),
                (over_delta, "UNHEDGED_DELTA_LIMIT"),
            ) if condition
        )
        return PairDecision(PairState.EMERGENCY_REDUCE_ONLY, net, ratio, reasons,
                            True, True, True, True)

    if primary_done and hedge_done:
        return PairDecision(PairState.BALANCED, net, ratio, ("PAIR_BALANCED",),
                            False, False, False, False)
    return PairDecision(PairState.HEDGE_PENDING, net, ratio, ("PAIR_FILL_IN_PROGRESS",),
                        True, True, False, False)


def expected_funding_pnl_usd(
    *, spot_notional_usd: float, perpetual_notional_usd: float,
    funding_rate: float, funding_receiving_side: str,
    estimated_total_cost_usd: float = 0.0,
) -> dict[str, float | bool]:
    """Estimate one funding interval only; not a profit guarantee.

    funding_receiving_side is 'short' when shorts receive from longs and 'long' when longs
    receive from shorts. This estimate excludes basis convergence/divergence and borrow.
    """
    vals = (spot_notional_usd, perpetual_notional_usd, funding_rate, estimated_total_cost_usd)
    if any(not math.isfinite(x) for x in vals) or min(spot_notional_usd, perpetual_notional_usd, estimated_total_cost_usd) < 0:
        raise ValueError("funding inputs must be finite and notionals/costs non-negative")
    if funding_receiving_side not in {"short", "long"}:
        raise ValueError("funding_receiving_side must be 'short' or 'long'")
    # Positive funding convention: longs pay shorts; negative: shorts pay longs.
    short_receives = funding_rate < 0
    receive = (funding_receiving_side == "short" and not short_receives) or (funding_receiving_side == "long" and short_receives)
    notional = min(spot_notional_usd, perpetual_notional_usd)
    gross = abs(funding_rate) * notional * (1.0 if receive else -1.0)
    net = gross - estimated_total_cost_usd
    return {
        "matched_notional_usd": notional,
        "funding_rate": funding_rate,
        "gross_funding_estimate_usd": gross,
        "estimated_total_cost_usd": estimated_total_cost_usd,
        "net_estimate_usd": net,
        "estimated_positive_after_costs": net > 0,
        "basis_and_borrow_risk_included": False,
    }
