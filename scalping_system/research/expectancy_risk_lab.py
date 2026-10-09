"""Research-only expectancy and risk-of-ruin calculator. Never connected to order execution."""
from __future__ import annotations

import math


def _probability(value: float) -> float:
    value = float(value)
    if not 0.0 < value < 1.0:
        raise ValueError("win_rate must be strictly between 0 and 1")
    return value


def _positive(value: float, name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and > 0")
    return value


def analyze_expectancy(
    win_rate: float = 0.45,
    reward_risk: float = 2.0,
    risk_fraction: float = 0.01,
    cost_r: float = 0.0,
    trades_per_month: float = 15.0,
) -> dict:
    """Analyze binary R-multiple outcomes; cost_r is the per-trade cost in R units."""
    p = _probability(win_rate)
    b = _positive(reward_risk, "reward_risk")
    f = _positive(risk_fraction, "risk_fraction")
    tpm = _positive(trades_per_month, "trades_per_month")
    c = float(cost_r)
    if not math.isfinite(c) or c < 0 or c >= b:
        raise ValueError("cost_r must be finite, >= 0, and smaller than reward_risk")
    if f * (1.0 + c) >= 1.0:
        raise ValueError("risk_fraction and costs permit a 100% loss or worse")

    q = 1.0 - p
    win_net_r = b - c
    loss_net_r = -1.0 - c
    expectancy_r = p * win_net_r + q * loss_net_r
    breakeven_win_rate = (1.0 + c) / (b + 1.0)
    log_growth = p * math.log1p(f * win_net_r) + q * math.log1p(f * loss_net_r)

    # Numerically maximize expected log growth over a conservative finite interval.
    upper = min(0.99 / (1.0 + c), 0.99)
    lo, hi = 0.0, upper
    phi = (math.sqrt(5.0) - 1.0) / 2.0

    def growth(frac: float) -> float:
        a = 1.0 + frac * win_net_r
        z = 1.0 + frac * loss_net_r
        if a <= 0 or z <= 0:
            return -math.inf
        return p * math.log(a) + q * math.log(z)

    x1 = hi - phi * (hi - lo)
    x2 = lo + phi * (hi - lo)
    for _ in range(120):
        if growth(x1) < growth(x2):
            lo, x1 = x1, x2
            x2 = lo + phi * (hi - lo)
        else:
            hi, x2 = x2, x1
            x1 = hi - phi * (hi - lo)
    kelly = (lo + hi) / 2.0
    if growth(kelly) <= 0:
        kelly = 0.0
    quarter_kelly = kelly / 4.0
    doubling_trades = math.log(2.0) / log_growth if log_growth > 0 else None

    return {
        "status": "RESEARCH_ONLY",
        "win_rate": p,
        "loss_rate": q,
        "reward_risk": b,
        "cost_r_per_trade": c,
        "net_expectancy_r_per_trade": expectancy_r,
        "breakeven_win_rate": breakeven_win_rate,
        "risk_fraction_per_trade": f,
        "expected_log_growth_per_trade": log_growth,
        "estimated_doubling_trades_at_assumed_distribution": doubling_trades,
        "estimated_doubling_months_at_assumed_trade_frequency": (
            doubling_trades / tpm if doubling_trades is not None else None
        ),
        "kelly_risk_fraction": kelly,
        "quarter_kelly_risk_fraction": quarter_kelly,
        "live_orders": False,
        "warning": "Estimates assume independent, stationary binary outcomes and known probabilities; real edge, costs, slippage, serial dependence, and tail risk must be validated out of sample.",
    }


def drawdown_recovery_gain(drawdown_fraction: float) -> float:
    """Gain required from a drawdown to return to the prior equity peak."""
    d = float(drawdown_fraction)
    if not math.isfinite(d) or d < 0 or d >= 1:
        raise ValueError("drawdown_fraction must be in [0, 1)")
    return d / (1.0 - d)


def risk_overlay(
    daily_return_fraction: float,
    peak_drawdown_fraction: float,
    previous_size_multiplier: float = 1.0,
    daily_stop_fraction: float = 0.02,
    max_drawdown_fraction: float = 0.10,
    recovery_drawdown_fraction: float = 0.05,
) -> dict:
    """Diagnostic-only circuit-breaker state; it does not place/close orders."""
    vals = (daily_return_fraction, peak_drawdown_fraction, previous_size_multiplier,
            daily_stop_fraction, max_drawdown_fraction, recovery_drawdown_fraction)
    if not all(math.isfinite(float(v)) for v in vals):
        raise ValueError("risk overlay inputs must be finite")
    if not 0 <= peak_drawdown_fraction < 1:
        raise ValueError("peak_drawdown_fraction must be in [0, 1)")
    if not 0 < daily_stop_fraction < 1:
        raise ValueError("daily_stop_fraction must be in (0, 1)")
    if not 0 < recovery_drawdown_fraction < max_drawdown_fraction < 1:
        raise ValueError("require 0 < recovery threshold < max drawdown threshold < 1")
    if previous_size_multiplier not in (0.5, 1.0):
        raise ValueError("previous_size_multiplier must be 0.5 or 1.0")

    daily_halt = daily_return_fraction <= -daily_stop_fraction
    if peak_drawdown_fraction >= max_drawdown_fraction:
        multiplier = 0.5
    elif previous_size_multiplier == 0.5 and peak_drawdown_fraction > recovery_drawdown_fraction:
        multiplier = 0.5
    else:
        multiplier = 1.0
    return {
        "daily_halt_required": daily_halt,
        "position_size_multiplier_for_future_trades": multiplier,
        "peak_drawdown_fraction": peak_drawdown_fraction,
        "research_only": True,
        "live_orders": False,
        "note": "Diagnostic only: daily_halt_required does not flatten positions or stop any process.",
    }


def main() -> None:
    import json
    result = analyze_expectancy()
    result["drawdown_recovery_examples"] = {
        str(int(d * 100)) + "%": drawdown_recovery_gain(d)
        for d in (0.10, 0.20, 0.30, 0.50, 0.75)
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
