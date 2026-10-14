"""Book-derived microstructure features for BTC scalping research.

Research/paper/replay only. No order placement.

Design basis:
- Limit orders are price-time queued; fill probability depends on queue ahead.
- Spread is a direct cost of immediacy.
- Resting liquidity can suffer adverse selection when short-term order flow
  predicts the next price move.
- Top-of-book imbalance can contain short-horizon information, but should be
  treated as a conditional feature, not a standalone predictor.

This module intentionally produces observable/proxy features. It does not
claim that any proxy is predictive until replay calibration validates it.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from math import isfinite
from typing import Any, Mapping, Sequence


def _f(value: Any, default: float = 0.0) -> float:
    try:
        x = float(value)
        return x if isfinite(x) else default
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class QueueFeature:
    side: str
    price: float
    queue_ahead: float
    same_price_total: float
    queue_fraction: float
    available: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MicropriceFeature:
    mid: float
    microprice: float
    displacement_bps: float
    directional_bias: float
    valid: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ImbalancePersistence:
    current: float
    mean: float
    aligned_fraction: float
    persistence: float
    flip: bool
    valid: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExecutionQuality:
    spread_bps: float | None
    quoted_half_spread_bps: float | None
    market_impact_bps: float
    adverse_selection_bps: float
    passive_edge_bps: float
    queue_fraction: float
    executable: bool
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _levels(book: Mapping[str, Any], key: str, *, reverse: bool) -> list[tuple[float, float]]:
    raw = book.get(key, {})
    if isinstance(raw, Mapping):
        rows = [(_f(p), _f(q)) for p, q in raw.items()]
    else:
        rows = [(_f(p), _f(q)) for p, q in raw]
    rows = [(p, q) for p, q in rows if p > 0 and q > 0]
    return sorted(rows, key=lambda x: x[0], reverse=reverse)


def best_quotes(book: Mapping[str, Any]) -> tuple[float, float]:
    bid = _f(book.get("best_bid"), 0.0)
    ask = _f(book.get("best_ask"), 0.0)
    if bid <= 0:
        bid = _f(book.get("bid"), 0.0)
    if ask <= 0:
        ask = _f(book.get("ask"), 0.0)

    bids = _levels(book, "bids", reverse=True)
    asks = _levels(book, "asks", reverse=False)
    if bid <= 0 and bids:
        bid = bids[0][0]
    if ask <= 0 and asks:
        ask = asks[0][0]
    return bid, ask


def estimate_queue(
    book: Mapping[str, Any],
    *,
    side: str,
    limit_price: float,
    own_size: float = 0.0,
) -> QueueFeature:
    """Estimate visible same-price quantity ahead of a new limit order.

    Under price-time priority, visible quantity already resting at our price
    is ahead of a newly submitted order. Hidden/other-venue liquidity and
    cancellations are not observable here, so this is a lower-bound proxy.
    """
    side = str(side).upper()
    if side == "BUY":
        rows = _levels(book, "bids", reverse=True)
    elif side == "SELL":
        rows = _levels(book, "asks", reverse=False)
    else:
        return QueueFeature(side, limit_price, 0.0, 0.0, 1.0, False)

    if limit_price <= 0 or not rows:
        return QueueFeature(side, limit_price, 0.0, 0.0, 1.0, False)

    tick = _f(book.get("tick_size"), 0.0)
    tolerance = max(tick / 2.0, abs(limit_price) * 1e-8)
    same = [q for p, q in rows if abs(p - limit_price) <= tolerance]
    total = sum(same)
    ahead = max(0.0, total)
    own = max(0.0, own_size)
    fraction = ahead / max(ahead + own, 1e-12)
    return QueueFeature(side, limit_price, ahead, total, fraction, True)


def microprice(book: Mapping[str, Any]) -> MicropriceFeature:
    """Depth-weighted top-of-book microprice and its displacement from mid.

    With bid size B and ask size A:
        microprice = (ask*B + bid*A) / (A+B)

    Positive displacement means the weighted pressure is toward the ask.
    """
    bid, ask = best_quotes(book)
    if bid <= 0 or ask <= bid:
        return MicropriceFeature(0.0, 0.0, 0.0, 0.0, False)

    bid_size = _f(book.get("bid_size"), 0.0)
    ask_size = _f(book.get("ask_size"), 0.0)

    if bid_size <= 0 or ask_size <= 0:
        bids = _levels(book, "bids", reverse=True)
        asks = _levels(book, "asks", reverse=False)
        bid_size = bids[0][1] if bids and abs(bids[0][0] - bid) < 1e-8 else bid_size
        ask_size = asks[0][1] if asks and abs(asks[0][0] - ask) < 1e-8 else ask_size

    total = bid_size + ask_size
    if total <= 0:
        return MicropriceFeature(0.0, 0.0, 0.0, 0.0, False)

    mid = (bid + ask) / 2.0
    mp = (ask * bid_size + bid * ask_size) / total
    displacement_bps = (mp - mid) / mid * 10000.0
    bias = (mp - mid) / max((ask - bid) / 2.0, 1e-12)
    return MicropriceFeature(mid, mp, displacement_bps, max(-1.0, min(1.0, bias)), True)


def imbalance_persistence(
    history: Sequence[float],
    *,
    side: str,
    min_abs: float = 0.10,
) -> ImbalancePersistence:
    """Measure whether book pressure has persisted in the trade direction."""
    vals = [_f(x, float("nan")) for x in history]
    vals = [x for x in vals if isfinite(x)]
    if not vals:
        return ImbalancePersistence(0.0, 0.0, 0.0, 0.0, False, False)

    side = str(side).upper()
    sign = 1.0 if side == "LONG" else -1.0
    aligned = [x * sign >= min_abs for x in vals]
    fraction = sum(aligned) / len(vals)
    mean = sum(vals) / len(vals)
    current = vals[-1]
    flip = any(
        vals[i - 1] * sign < -min_abs and vals[i] * sign >= min_abs
        for i in range(1, len(vals))
    )
    persistence = fraction * min(1.0, abs(mean) / max(min_abs, 1e-12))
    return ImbalancePersistence(
        current=current,
        mean=mean,
        aligned_fraction=fraction,
        persistence=max(0.0, min(1.0, persistence)),
        flip=flip,
        valid=len(vals) >= 2,
    )


def execution_quality(
    book: Mapping[str, Any],
    *,
    side: str,
    limit_price: float | None = None,
    order_size: float = 0.0,
    predicted_move_bps: float = 0.0,
    queue: QueueFeature | None = None,
    micro: MicropriceFeature | None = None,
    impact_coefficient_bps: float = 1.0,
) -> ExecutionQuality:
    """Build a conservative execution-quality screen.

    market_impact_bps is a proxy based on order size / visible top-N depth.
    adverse_selection_bps uses microprice displacement against a passive side.
    Both require replay calibration before being used as calibrated forecasts.
    """
    bid, ask = best_quotes(book)
    if bid <= 0 or ask <= bid:
        return ExecutionQuality(None, None, 0.0, 0.0, 0.0,
                                queue.queue_fraction if queue else 1.0,
                                False, ("QUOTES_UNAVAILABLE",))

    mid = (bid + ask) / 2.0
    spread_bps = (ask - bid) / mid * 10000.0
    half_bps = spread_bps / 2.0

    levels = _levels(book, "bids" if str(side).upper() == "SELL" else "asks",
                     reverse=str(side).upper() == "SELL")
    visible_depth = sum(q for _, q in levels[:5])
    impact = 0.0
    if order_size > 0 and visible_depth > 0:
        impact = impact_coefficient_bps * order_size / visible_depth * 10000.0

    micro = micro or microprice(book)
    sign = 1.0 if str(side).upper() == "LONG" else -1.0
    # For a passive long, upward microprice pressure is favourable; for short,
    # downward pressure is favourable. Opposite pressure is adverse selection.
    adverse = max(0.0, -micro.displacement_bps * sign) if micro.valid else 0.0
    passive_edge = predicted_move_bps - spread_bps - impact - adverse

    reasons: list[str] = []
    if spread_bps <= 5.0:
        reasons.append("SPREAD_TIGHT")
    else:
        reasons.append("SPREAD_WIDE")
    if impact <= 2.0:
        reasons.append("IMPACT_LOW")
    else:
        reasons.append("IMPACT_ELEVATED")
    if adverse <= 1.0:
        reasons.append("ADVERSE_SELECTION_LOW")
    else:
        reasons.append("ADVERSE_SELECTION_ELEVATED")
    if queue is not None:
        reasons.append("QUEUE_ESTIMATED")

    executable = (
        spread_bps <= 5.0
        and passive_edge > 0.0
        and adverse <= max(2.0, abs(predicted_move_bps) * 0.50)
    )
    return ExecutionQuality(
        spread_bps=spread_bps,
        quoted_half_spread_bps=half_bps,
        market_impact_bps=impact,
        adverse_selection_bps=adverse,
        passive_edge_bps=passive_edge,
        queue_fraction=queue.queue_fraction if queue else 1.0,
        executable=executable,
        reasons=tuple(reasons),
    )
