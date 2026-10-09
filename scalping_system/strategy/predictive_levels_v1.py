"""Dynamic predictive support/resistance for BTC paper execution.

Research/paper-only. Levels are probability-weighted reference zones, not
guaranteed future prices. Uses recent OHLCV, volume-profile acceptance,
swing structure and current order-book depth.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from math import sqrt
from statistics import median
from typing import Iterable


@dataclass(frozen=True)
class Level:
    price: float
    kind: str
    strength: float
    distance_bps: float
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class PredictiveLevels:
    price: float
    atr: float
    atr_pct: float
    support: tuple[Level, ...]
    resistance: tuple[Level, ...]
    nearest_support: float | None
    nearest_resistance: float | None
    value_low: float | None
    poc: float | None
    value_high: float | None
    regime: str

    def to_dict(self) -> dict:
        return asdict(self)


def _f(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _candle_rows(candles: Iterable[dict]) -> list[dict]:
    rows = []
    for c in candles:
        o, h, l, close, v = (_f(c.get(k)) for k in ("open", "high", "low", "close", "volume"))
        if h > 0 and l > 0 and close > 0 and h >= l:
            rows.append({"open": o, "high": h, "low": l, "close": close, "volume": max(v, 0.0)})
    return rows


def _atr(rows: list[dict], period: int = 14) -> float:
    if not rows:
        return 0.0
    trs = []
    prev = None
    for c in rows[-period - 1:]:
        if prev is None:
            tr = c["high"] - c["low"]
        else:
            tr = max(c["high"] - c["low"], abs(c["high"] - prev), abs(c["low"] - prev))
        trs.append(max(tr, 0.0))
        prev = c["close"]
    return sum(trs[-period:]) / max(1, min(period, len(trs)))


def _profile(rows: list[dict], bins: int = 48) -> tuple[float | None, float | None, float | None]:
    if not rows:
        return None, None, None
    lo = min(c["low"] for c in rows)
    hi = max(c["high"] for c in rows)
    if hi <= lo:
        return lo, lo, hi
    step = (hi - lo) / bins
    volumes = [0.0] * bins
    for c in rows:
        # Distribute candle volume across touched bins. This is an approximation
        # that remains stable when tick-level historical volume is unavailable.
        first = max(0, min(bins - 1, int((c["low"] - lo) / step)))
        last = max(0, min(bins - 1, int((c["high"] - lo) / step)))
        count = max(1, last - first + 1)
        share = c["volume"] / count
        for i in range(first, last + 1):
            volumes[i] += share
    order = sorted(range(bins), key=lambda i: volumes[i], reverse=True)
    poc_i = order[0]
    total = sum(volumes)
    target = total * 0.70
    selected = {poc_i}
    covered = volumes[poc_i]
    while covered < target and len(selected) < bins:
        candidates = [i for i in (min(selected) - 1, max(selected) + 1) if 0 <= i < bins and i not in selected]
        if not candidates:
            break
        i = max(candidates, key=lambda j: volumes[j])
        selected.add(i)
        covered += volumes[i]
    poc = lo + (poc_i + 0.5) * step
    val = lo + (min(selected) + 0.5) * step
    vah = lo + (max(selected) + 0.5) * step
    return val, poc, vah


def _cluster(values: list[tuple[float, str, float]], tolerance: float) -> list[tuple[float, list[str], float]]:
    groups: list[tuple[float, list[str], float]] = []
    for price, evidence, weight in sorted(values):
        if not groups or abs(price - groups[-1][0]) > tolerance:
            groups.append((price, [evidence], weight))
        else:
            p, ev, w = groups[-1]
            nw = w + weight
            groups[-1] = ((p * w + price * weight) / nw, ev + [evidence], nw)
    return groups


def compute_levels(candles: Iterable[dict], current_price: float, order_book: dict | None = None,
                   lookback: int = 240, bins: int = 48) -> PredictiveLevels:
    rows = _candle_rows(candles)[-lookback:]
    px = _f(current_price)
    atr = _atr(rows)
    if not rows or px <= 0:
        return PredictiveLevels(px, atr, atr / px * 100 if px else 0, (), (), None, None, None, None, None, "UNKNOWN")

    val, poc, vah = _profile(rows, bins=bins)
    tolerance = max(atr * 0.20, px * 0.0007)

    candidates: list[tuple[float, str, float]] = []
    for c in rows[-80:]:
        candidates.extend([
            (c["low"], "SWING_LOW", 1.0),
            (c["high"], "SWING_HIGH", 1.0),
        ])

    if val is not None:
        candidates.append((val, "VALUE_LOW", 1.6))
    if poc is not None:
        candidates.append((poc, "POC_HVN", 1.8))
    if vah is not None:
        candidates.append((vah, "VALUE_HIGH", 1.6))

    ob = order_book or {}
    bid = _f(ob.get("best_bid"))
    ask = _f(ob.get("best_ask"))
    bid_depth = _f(ob.get("bid_depth_5"))
    ask_depth = _f(ob.get("ask_depth_5"))
    if bid > 0 and bid_depth > 0:
        candidates.append((bid, "BID_LIQUIDITY", 1.2))
    if ask > 0 and ask_depth > 0:
        candidates.append((ask, "ASK_LIQUIDITY", 1.2))

    # If live price has moved outside the historical candle window, project
    # explicit volatility bands so the engine still has nearby levels.
    if not any(p < px for p, _, _ in candidates):
        candidates.append((px - max(atr, px * 0.001), "ATR_SUPPORT_PROJECTION", 0.75))
        candidates.append((px - max(2.0 * atr, px * 0.002), "ATR_SUPPORT_PROJECTION", 0.55))
    if not any(p > px for p, _, _ in candidates):
        candidates.append((px + max(atr, px * 0.001), "ATR_RESISTANCE_PROJECTION", 0.75))
        candidates.append((px + max(2.0 * atr, px * 0.002), "ATR_RESISTANCE_PROJECTION", 0.55))

    groups = _cluster(candidates, tolerance)
    supports: list[Level] = []
    resistances: list[Level] = []

    for level_price, evidence, weight in groups:
        if level_price <= 0:
            continue
        dist_bps = (level_price / px - 1.0) * 10000.0
        # Distance decay keeps very remote historical levels from dominating.
        decay = max(0.20, 1.0 / (1.0 + abs(dist_bps) / 100.0))
        strength = min(100.0, 35.0 + 12.0 * weight + 45.0 * decay)
        unique_evidence = tuple(dict.fromkeys(evidence))
        level = Level(round(level_price, 2), "SUPPORT" if level_price < px else "RESISTANCE",
                      round(strength, 1), round(dist_bps, 2), unique_evidence)
        if level_price < px:
            supports.append(level)
        elif level_price > px:
            resistances.append(level)

    if not supports:
        fallback = bid if bid > 0 and bid < px else px - max(atr, px * 0.001)
        supports.append(Level(round(fallback, 2), "SUPPORT", 50.0,
                              round((fallback / px - 1.0) * 10000.0, 2),
                              ("BID_LIQUIDITY_FALLBACK" if bid > 0 and bid < px else "ATR_SUPPORT_PROJECTION",)))
    if not resistances:
        fallback = ask if ask > px else px + max(atr, px * 0.001)
        resistances.append(Level(round(fallback, 2), "RESISTANCE", 50.0,
                                 round((fallback / px - 1.0) * 10000.0, 2),
                                 ("ASK_LIQUIDITY_FALLBACK" if ask > px else "ATR_RESISTANCE_PROJECTION",)))

    supports.sort(key=lambda x: abs(x.distance_bps))
    resistances.sort(key=lambda x: abs(x.distance_bps))

    atr_pct = atr / px * 100.0
    if atr_pct >= 1.8:
        regime = "HIGH_VOLATILITY"
    elif atr_pct <= 0.7:
        regime = "LOW_VOLATILITY"
    else:
        regime = "NORMAL_VOLATILITY"

    return PredictiveLevels(
        price=px, atr=round(atr, 4), atr_pct=round(atr_pct, 4),
        support=tuple(supports[:8]), resistance=tuple(resistances[:8]),
        nearest_support=supports[0].price if supports else None,
        nearest_resistance=resistances[0].price if resistances else None,
        value_low=val, poc=poc, value_high=vah, regime=regime,
    )


def level_context(levels: PredictiveLevels, side: str, max_distance_atr: float = 1.25) -> dict:
    """Return a deterministic gate/context for a proposed LONG/SHORT."""
    target = levels.nearest_support if side == "LONG" else levels.nearest_resistance
    if target is None or levels.atr <= 0:
        return {"eligible": False, "reason": "NO_NEAR_LEVEL"}
    distance = abs(levels.price - target)
    near = distance <= levels.atr * max_distance_atr
    return {
        "eligible": near,
        "reason": "NEAR_PREDICTIVE_LEVEL" if near else "TOO_FAR_FROM_LEVEL",
        "level": target,
        "distance": round(distance, 4),
        "distance_atr": round(distance / levels.atr, 3),
        "atr": levels.atr,
        "atr_pct": levels.atr_pct,
    }
