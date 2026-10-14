"""Advanced BTC market predictor v1: empirical quantiles + optional conformal calibration.

Research/paper-only baseline. No neural model is trained and no orders are sent.
All candle inputs must be completed bars; probabilities are empirical frequencies,
not guaranteed or calibrated probabilities. Keep separate from production strategy.
"""
from __future__ import annotations

from math import isfinite, log
from statistics import pstdev
from typing import Iterable, Mapping, Sequence


def _finite(value, default=None):
    try:
        x = float(value)
    except (TypeError, ValueError):
        return default
    return x if isfinite(x) else default


def _quantile(values: Sequence[float], q: float) -> float:
    if not values:
        raise ValueError("quantile requires observations")
    if not 0.0 <= q <= 1.0:
        raise ValueError("q must be between 0 and 1")
    xs = sorted(values)
    pos = (len(xs) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def order_book_imbalance(order_book: Mapping | None, levels: int = 5) -> float | None:
    """Compute (bid depth - ask depth)/(bid depth + ask depth), for top N levels."""
    if not order_book or levels < 1:
        return None

    def depth(side):
        raw = order_book.get(side, [])
        total = 0.0
        for item in list(raw)[:levels]:
            try:
                size = item.get("size", item.get("quantity", item.get("volume", 0))) if isinstance(item, Mapping) else item[1]
                size = _finite(size, 0.0)
                if size is not None and size > 0:
                    total += size
            except (IndexError, TypeError):
                continue
        return total

    bid, ask = depth("buy"), depth("sell")
    denom = bid + ask
    return (bid - ask) / denom if denom > 0 else None


def _closed_closes(candles: Iterable[Mapping]) -> list[float]:
    closes = []
    for candle in candles:
        if candle.get("closed", True) is False:
            continue
        close = _finite(candle.get("close"))
        if close is not None and close > 0:
            closes.append(close)
    return closes


def _conformal_radius(errors: Sequence[float], alpha: float) -> float | None:
    """Finite-sample absolute-error radius; needs independent calibration residuals."""
    if not errors:
        return None
    valid = [abs(float(e)) for e in errors if _finite(e) is not None]
    if not valid:
        return None
    rank = min(len(valid), max(1, int((len(valid) + 1) * (1.0 - alpha) + 0.999999)))
    return sorted(valid)[rank - 1]


def forecast(candles: Iterable[Mapping], order_book: Mapping | None = None,
             horizon: int = 5, calibration_errors: Sequence[float] | None = None,
             cost_bps: float = 12.0, min_samples: int = 100,
             obi_levels: int = 5) -> dict:
    """Forecast horizon-period close-to-close return from completed candles only.

    calibration_errors must be untouched chronological calibration residuals in
    percentage points of return (not bps). The current price is the latest close.
    """
    if horizon < 1:
        raise ValueError("horizon must be >= 1")
    if cost_bps < 0:
        raise ValueError("cost_bps must be >= 0")
    closes = _closed_closes(candles)
    if len(closes) < horizon + 2:
        return {"status": "INSUFFICIENT_DATA", "samples": 0, "paper_only": True,
                "order_submission": False}

    # Historical horizon returns ending at or before the latest close; simple empirical baseline.
    returns = [(log(closes[i] / closes[i - horizon]) * 100.0)
               for i in range(horizon, len(closes))]
    returns = [r for r in returns if isfinite(r)]
    current_price = closes[-1]
    latest_momentum = log(closes[-1] / closes[-1 - horizon]) * 100.0
    recent = [log(closes[i] / closes[i - 1]) * 100.0
              for i in range(max(1, len(closes) - 20), len(closes))]
    vol = pstdev(recent) if len(recent) > 1 else 0.0
    obi = order_book_imbalance(order_book, obi_levels)
    enough = len(returns) >= min_samples

    if not returns:
        return {"status": "INSUFFICIENT_DATA", "samples": 0, "paper_only": True,
                "order_submission": False}

    q10, q50, q90 = (_quantile(returns, q) for q in (0.10, 0.50, 0.90))
    radius = _conformal_radius(calibration_errors or (), 0.20)
    low = q10 - radius if radius is not None else q10
    high = q90 + radius if radius is not None else q90
    p_up = sum(r > 0 for r in returns) / len(returns)
    p_down = sum(r < 0 for r in returns) / len(returns)
    cost_pct = cost_bps / 100.0
    direction = "FLAT"
    vetoes = []
    if not enough:
        vetoes.append("INSUFFICIENT_TRAINING_SAMPLE")
    if radius is None:
        vetoes.append("UNCALIBRATED_INTERVAL")
    if q50 > cost_pct and p_up > 0.55 and (obi is None or obi >= 0):
        direction = "UP" if enough else "FLAT"
    elif q50 < -cost_pct and p_down > 0.55 and (obi is None or obi <= 0):
        direction = "DOWN" if enough else "FLAT"
    if obi is not None and ((direction == "UP" and obi < -0.10) or
                            (direction == "DOWN" and obi > 0.10)):
        direction = "FLAT"
        vetoes.append("ORDER_BOOK_IMBALANCE_CONFLICT")

    return {
        "status": "RESEARCH_ONLY" if enough else "INSUFFICIENT_DATA",
        "instrument_scope": "BTC perpetual research; caller must confirm venue/contract",
        "horizon_bars": horizon,
        "current_price": current_price,
        "samples": len(returns),
        "return_quantiles_pct": {"q10": q10, "q50": q50, "q90": q90},
        "prediction_interval_pct": {"low": low, "high": high, "nominal_coverage": 0.80,
                                    "calibrated": radius is not None,
                                    "calibration_residual_count": len(calibration_errors or ())},
        "empirical_direction_frequency_pct": {"up": p_up * 100, "down": p_down * 100},
        "momentum_pct": latest_momentum,
        "recent_volatility_pct_per_bar": vol,
        "order_book_imbalance": obi,
        "cost_assumption_bps": cost_bps,
        "direction": direction,
        "vetoes": vetoes,
        "warnings": [
            "Empirical frequencies are not calibrated future probabilities.",
            "Intervals are not coverage-guaranteed; conformal validity depends on exchangeability.",
            "Overlapping horizon returns are dependent; use purged walk-forward validation.",
            "This baseline is not a trained neural state-space model."
        ],
        "paper_only": True,
        "order_submission": False,
        "promotion_allowed": False
    }


def pinball_loss(actual: float, predicted_quantile: float, alpha: float) -> float:
    """Quantile regression loss, useful for evaluating forecasts out of sample."""
    error = actual - predicted_quantile
    return max(alpha * error, (alpha - 1.0) * error)
