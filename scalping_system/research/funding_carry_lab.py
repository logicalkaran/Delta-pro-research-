"""Funding-carry research calculator. Offline only; no exchange or order API."""
from __future__ import annotations

import math
from typing import Iterable


def _finite(value: float, name: str) -> float:
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return value


def funding_yield(rate_per_8h: float, epochs: int = 3) -> dict:
    """Return funding-only yields; positive funding benefits a short perp."""
    rate = _finite(rate_per_8h, "rate_per_8h")
    if not isinstance(epochs, int) or epochs < 1:
        raise ValueError("epochs must be a positive integer")
    daily_simple = rate * epochs
    annual_simple = daily_simple * 365
    annual_compounded = (1 + rate) ** (epochs * 365) - 1 if rate > -1 else float("nan")
    return {
        "rate_per_8h": rate,
        "daily_simple_yield": daily_simple,
        "annual_simple_yield": annual_simple,
        "annual_compounded_yield": annual_compounded,
        "short_receives_funding_when_rate_positive": rate > 0,
        "assumes_constant_rate": True,
        "paper_only": True,
    }


def round_trip_friction_bps(
    *, spot_fee_bps: float, perp_entry_fee_bps: float,
    perp_exit_fee_bps: float, spot_exit_fee_bps: float,
    spread_slippage_bps: float = 0.0,
) -> float:
    """Sum four leg fees plus an explicit aggregate spread/slippage allowance."""
    values = {
        "spot_fee_bps": spot_fee_bps,
        "perp_entry_fee_bps": perp_entry_fee_bps,
        "perp_exit_fee_bps": perp_exit_fee_bps,
        "spot_exit_fee_bps": spot_exit_fee_bps,
        "spread_slippage_bps": spread_slippage_bps,
    }
    total = 0.0
    for name, raw in values.items():
        value = _finite(raw, name)
        if value < 0:
            raise ValueError(f"{name} must be >= 0")
        total += value
    return total


def breakeven_funding_epochs(
    *, round_trip_cost_bps: float, funding_rate_per_8h: float,
    basis_convergence_bps: float = 0.0,
) -> dict:
    """Funding-only breakeven, excluding capital opportunity cost and changing rates."""
    cost = _finite(round_trip_cost_bps, "round_trip_cost_bps")
    rate = _finite(funding_rate_per_8h, "funding_rate_per_8h")
    basis = _finite(basis_convergence_bps, "basis_convergence_bps")
    if cost < 0 or basis < 0:
        raise ValueError("cost and basis convergence must be >= 0")
    if rate <= 0:
        return {"status": "NO_POSITIVE_FUNDING_EDGE", "epochs": None, "days": None,
                "paper_only": True}
    residual = max(0.0, cost - basis)
    epochs = math.ceil(residual / (rate * 10000)) if residual else 0
    return {
        "status": "ESTIMATE_ONLY",
        "round_trip_cost_bps": cost,
        "basis_convergence_credit_bps": basis,
        "net_cost_after_basis_bps": residual,
        "funding_bps_per_epoch": rate * 10000,
        "epochs": epochs,
        "days_at_three_epochs_per_day": epochs / 3,
        "paper_only": True,
    }


def short_liquidation_boundary(leverage: float, maintenance_margin_rate: float = 0.005) -> dict:
    """Simplified linear isolated-margin estimate; not an exchange liquidation formula."""
    leverage = _finite(leverage, "leverage")
    mmr = _finite(maintenance_margin_rate, "maintenance_margin_rate")
    if leverage < 1 or mmr < 0 or mmr >= 1:
        raise ValueError("leverage must be >= 1 and MMR must be in [0,1)")
    tolerance = 1 / leverage - mmr
    price_multiple = 1 + tolerance
    return {
        "leverage": leverage,
        "maintenance_margin_rate": mmr,
        "estimated_upward_tolerance_fraction": tolerance,
        "estimated_liquidation_price_multiple": price_multiple,
        "valid_estimate": tolerance > 0,
        "warning": "Simplified linear estimate; actual exchange tiers, fees, funding and margin rules differ.",
        "paper_only": True,
    }


def margin_health(
    *, entry_price: float, mark_price: float, size_btc: float,
    isolated_margin: float, maintenance_margin_rate: float = 0.005,
    rebalance_threshold: float = 0.30,
) -> dict:
    """Diagnostic short-perp margin buffer; never transfers collateral or closes positions."""
    entry = _finite(entry_price, "entry_price")
    mark = _finite(mark_price, "mark_price")
    size = _finite(size_btc, "size_btc")
    margin = _finite(isolated_margin, "isolated_margin")
    mmr = _finite(maintenance_margin_rate, "maintenance_margin_rate")
    threshold = _finite(rebalance_threshold, "rebalance_threshold")
    if min(entry, mark, size, margin) <= 0:
        raise ValueError("prices, size and margin must be > 0")
    if not 0 <= mmr < 1 or not 0 <= threshold <= 1:
        raise ValueError("MMR and threshold must be in [0,1)")
    unrealized = (entry - mark) * size
    remaining = margin + unrealized
    maintenance = mark * size * mmr
    buffer = remaining - maintenance
    health = buffer / margin
    return {
        "unrealized_short_pnl": unrealized,
        "remaining_margin_before_fees": remaining,
        "maintenance_margin_estimate": maintenance,
        "buffer_after_maintenance": buffer,
        "health_buffer_fraction_of_initial_margin": health,
        "action": "REVIEW_MARGIN_IMMEDIATELY" if health <= threshold else "HOLD_DIAGNOSTIC",
        "can_be_liquidated": buffer <= 0,
        "spot_gain_does_not_auto_fund_perp_margin": True,
        "paper_only": True,
        "real_orders": False,
    }


def funding_continuation(rates: Iterable[float], minimum_average: float = 0.0) -> dict:
    values = [_finite(rate, "funding_rate") for rate in rates]
    minimum = _finite(minimum_average, "minimum_average")
    if not values:
        raise ValueError("at least one funding observation is required")
    average = sum(values) / len(values)
    return {
        "observations": len(values),
        "average_funding_rate": average,
        "action": "REVIEW_UNWIND" if average <= minimum else "HOLD_RESEARCH",
        "paper_only": True,
        "note": "Diagnostic only; unwind requires a separate approved execution process.",
    }


def main() -> None:
    fees = round_trip_friction_bps(
        spot_fee_bps=10, perp_entry_fee_bps=2, perp_exit_fee_bps=2,
        spot_exit_fee_bps=10,
    )
    print("status RESEARCH_ONLY")
    print("funding_0.02pct_8h", funding_yield(0.0002))
    print("round_trip_cost_bps", fees)
    print("breakeven", breakeven_funding_epochs(
        round_trip_cost_bps=fees, funding_rate_per_8h=0.0002))
    for leverage in (1, 2, 3, 5):
        print("short_liquidation_estimate", short_liquidation_boundary(leverage))
    print("live_orders false")


if __name__ == "__main__":
    main()
