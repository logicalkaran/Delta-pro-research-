"""Institutional absorption/divergence scalper derived from the uploaded BTC microstructure guide.

Paper/shadow layer only. It never submits orders.
Core idea:
- 1m execution structure with 5m bias/context.
- Price takes a local extreme.
- CVD/trade-flow moves aggressively into the extreme.
- Open interest is flat/down on the attempted continuation.
- Price rejects the extreme (absorption).
- Stop = 1.5 * ATR beyond the rejection wick.
- TP = local POC only when it provides >= 2R.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence


@dataclass(frozen=True)
class AbsorptionConfig:
    lookback_1m: int = 20
    min_cvd_abs_pct_30s: float = 0.08
    max_oi_rise_pct: float = 0.02
    min_rejection_fraction: float = 0.35
    atr_period: int = 14
    stop_atr_multiple: float = 1.5
    min_rr: float = 2.0
    max_spread_bps: float = 5.0
    max_fresh_seconds: float = 2.0
    min_candle_range_atr: float = 0.15


@dataclass(frozen=True)
class AbsorptionSignal:
    action: str
    confidence: float
    reason: tuple[str, ...]
    entry: float
    stop: float | None
    target: float | None
    risk: float | None
    reward: float | None
    rr: float | None
    atr: float
    swing_price: float | None
    cvd_pressure: float
    oi_change_pct: float
    rejection: float
    five_min_bias: str
    valid: bool


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _close(c: dict) -> float:
    return _f(c.get("close"))


def atr(candles: Sequence[dict], period: int = 14) -> float:
    rows = list(candles)[-max(2, period + 1):]
    if not rows:
        return 0.0
    trs = []
    prev = None
    for c in rows:
        h, l = _f(c.get("high")), _f(c.get("low"))
        if h <= 0 or l <= 0 or h < l:
            continue
        if prev is None:
            tr = h - l
        else:
            tr = max(h - l, abs(h - prev), abs(l - prev))
        trs.append(max(tr, 0.0))
        prev = _close(c)
    if not trs:
        return 0.0
    return sum(trs[-period:]) / min(period, len(trs))


def _poc(candles: Sequence[dict], bins: int = 48) -> float | None:
    rows = [c for c in candles if _f(c.get("high")) > 0 and _f(c.get("low")) > 0]
    if not rows:
        return None
    lo = min(_f(c["low"]) for c in rows)
    hi = max(_f(c["high"]) for c in rows)
    if hi <= lo:
        return lo
    step = (hi - lo) / bins
    volumes = [0.0] * bins
    for c in rows:
        first = max(0, min(bins - 1, int((_f(c["low"]) - lo) / step)))
        last = max(0, min(bins - 1, int((_f(c["high"]) - lo) / step)))
        share = max(_f(c.get("volume")), 0.0) / max(1, last - first + 1)
        for i in range(first, last + 1):
            volumes[i] += share
    i = max(range(bins), key=volumes.__getitem__)
    return lo + (i + 0.5) * step


def _bias(candles_5m: Sequence[dict]) -> str:
    rows = list(candles_5m)
    if len(rows) < 3:
        return "UNKNOWN"
    closes = [_close(x) for x in rows[-6:] if _close(x) > 0]
    if len(closes) < 3:
        return "UNKNOWN"
    if closes[-1] > max(closes[:-1]):
        return "BULLISH"
    if closes[-1] < min(closes[:-1]):
        return "BEARISH"
    return "NEUTRAL"


def _default_result(action: str, reason: list[str], entry: float, atr_value: float,
                    cvd: float, oi: float, rejection: float, bias: str) -> AbsorptionSignal:
    return AbsorptionSignal(action, 0.0, tuple(reason), entry, None, None, None, None, None,
                            atr_value, None, cvd, oi, rejection, bias, False)


def evaluate(
    micro: dict,
    candles_1m: Sequence[dict],
    candles_5m: Sequence[dict] | None = None,
    oi_change_pct: float = 0.0,
    poc: float | None = None,
    cfg: AbsorptionConfig = AbsorptionConfig(),
) -> AbsorptionSignal:
    candles_1m = list(candles_1m)[-cfg.lookback_1m:]
    candles_5m = list(candles_5m or [])
    ob = micro.get("order_book", {})
    quality = micro.get("quality", {})
    price = _f(ob.get("mid_price") or micro.get("last_price"))
    spread = _f(ob.get("spread"))
    fresh = _f(quality.get("fresh_seconds"), 999.0)
    atr_value = atr(candles_1m, cfg.atr_period)
    bias = _bias(candles_5m)

    if price <= 0 or atr_value <= 0:
        return _default_result("NO_TRADE", ["INSUFFICIENT_PRICE_OR_ATR"], price, atr_value, 0, oi_change_pct, 0, bias)
    spread_bps = spread / price * 10000 if price else 999
    if fresh > cfg.max_fresh_seconds:
        return _default_result("NO_TRADE", ["STALE_MICROSTRUCTURE"], price, atr_value, 0, oi_change_pct, 0, bias)
    if spread_bps > cfg.max_spread_bps:
        return _default_result("NO_TRADE", ["SPREAD_BLOCK"], price, atr_value, 0, oi_change_pct, 0, bias)
    if len(candles_1m) < max(5, cfg.atr_period):
        return _default_result("NO_TRADE", ["INSUFFICIENT_1M_HISTORY"], price, atr_value, 0, oi_change_pct, 0, bias)

    last = candles_1m[-1]
    high = _f(last.get("high"))
    low = _f(last.get("low"))
    close = _close(last)
    candle_range = max(high - low, 0.0)
    if candle_range < atr_value * cfg.min_candle_range_atr:
        return _default_result("NO_TRADE", ["TINY_1M_RANGE"], price, atr_value, 0, oi_change_pct, 0, bias)

    previous = candles_1m[:-1]
    prev_low = min(_f(c.get("low")) for c in previous[-10:])
    prev_high = max(_f(c.get("high")) for c in previous[-10:])
    new_low = low < prev_low
    new_high = high > prev_high

    # Positive rejection means price closed away from the extreme.
    long_rejection = max(0.0, (close - low) / candle_range)
    short_rejection = max(0.0, (high - close) / candle_range)

    w30 = micro.get("windows", {}).get("30", {})
    delta30 = _f(w30.get("delta_pct"))
    # Keep CVD pressure dimensionless. The live collector exposes raw CVD slope,
    # so only use it when a normalized percentage field is explicitly present.
    cvd_slope_pct = _f(micro.get("cvd_slope_30s_pct"), delta30)
    cvd_pressure = cvd_slope_pct

    # Long: aggressive selling/CVD down + OI flat/down + failed downside extension.
    long_absorption = (
        new_low
        and cvd_pressure <= -cfg.min_cvd_abs_pct_30s
        and oi_change_pct <= cfg.max_oi_rise_pct
        and long_rejection >= cfg.min_rejection_fraction
    )
    # Short: aggressive buying/CVD up + OI flat/down + failed upside extension.
    short_absorption = (
        new_high
        and cvd_pressure >= cfg.min_cvd_abs_pct_30s
        and oi_change_pct <= cfg.max_oi_rise_pct
        and short_rejection >= cfg.min_rejection_fraction
    )

    target = poc if poc and poc > 0 else _poc(candles_1m)

    if long_absorption:
        stop = low - cfg.stop_atr_multiple * atr_value
        reward = (target - price) if target is not None else 0.0
        risk = price - stop
        rr = reward / risk if risk > 0 else 0.0
        reasons = ["NEW_1M_LOW", "CVD_SELLING_PRESSURE", "OI_FLAT_OR_DOWN", "BUYER_ABSORPTION"]
        if bias in ("BULLISH", "NEUTRAL"):
            reasons.append("5M_BIAS_SUPPORT")
        if target is None or target <= price:
            reasons.append("POC_NOT_ABOVE_ENTRY")
            return _default_result("NO_TRADE", reasons, price, atr_value, cvd_pressure, oi_change_pct, long_rejection, bias)
        if rr < cfg.min_rr:
            reasons.append("POC_RR_BELOW_2")
            return _default_result("NO_TRADE", reasons, price, atr_value, cvd_pressure, oi_change_pct, long_rejection, bias)
        confidence = min(0.99, 0.55 + min(long_rejection, 1.0) * 0.15 + min(abs(cvd_pressure), 1.0) * 0.15)
        return AbsorptionSignal("LONG", confidence, tuple(reasons), price, stop, target, risk, reward, rr,
                                atr_value, low, cvd_pressure, oi_change_pct, long_rejection, bias, True)

    if short_absorption:
        stop = high + cfg.stop_atr_multiple * atr_value
        reward = (price - target) if target is not None else 0.0
        risk = stop - price
        rr = reward / risk if risk > 0 else 0.0
        reasons = ["NEW_1M_HIGH", "CVD_BUYING_PRESSURE", "OI_FLAT_OR_DOWN", "SELLER_ABSORPTION"]
        if bias in ("BEARISH", "NEUTRAL"):
            reasons.append("5M_BIAS_SUPPORT")
        if target is None or target >= price:
            reasons.append("POC_NOT_BELOW_ENTRY")
            return _default_result("NO_TRADE", reasons, price, atr_value, cvd_pressure, oi_change_pct, short_rejection, bias)
        if rr < cfg.min_rr:
            reasons.append("POC_RR_BELOW_2")
            return _default_result("NO_TRADE", reasons, price, atr_value, cvd_pressure, oi_change_pct, short_rejection, bias)
        confidence = min(0.99, 0.55 + min(short_rejection, 1.0) * 0.15 + min(abs(cvd_pressure), 1.0) * 0.15)
        return AbsorptionSignal("SHORT", confidence, tuple(reasons), price, stop, target, risk, reward, rr,
                                atr_value, high, cvd_pressure, oi_change_pct, short_rejection, bias, True)

    # Preserve the trading decision, but expose the exact failed components so
    # production monitoring can distinguish a genuinely absent setup from a
    # feature/threshold problem. This is telemetry only; acceptance rules above
    # are unchanged.
    detail = []
    if not new_low and not new_high:
        detail.append("NO_LOCAL_SWEEP")
    elif new_low and not (cvd_pressure <= -cfg.min_cvd_abs_pct_30s):
        detail.append("LONG_CVD_NOT_EXTREME")
    elif new_high and not (cvd_pressure >= cfg.min_cvd_abs_pct_30s):
        detail.append("SHORT_CVD_NOT_EXTREME")
    if (new_low or new_high) and oi_change_pct > cfg.max_oi_rise_pct:
        detail.append("OI_RISING")
    if new_low and long_rejection < cfg.min_rejection_fraction:
        detail.append("LONG_REJECTION_WEAK")
    if new_high and short_rejection < cfg.min_rejection_fraction:
        detail.append("SHORT_REJECTION_WEAK")
    if not detail:
        detail.append("ABSORPTION_CONDITIONS_NOT_ALIGNED")
    return _default_result("NO_TRADE", ["NO_ABSORPTION_PATTERN", *detail], price, atr_value, cvd_pressure, oi_change_pct,
                           max(long_rejection, short_rejection), bias)
