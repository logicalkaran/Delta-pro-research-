"""Deterministic BTC scalping feature layer.

Paper/shadow/replay only. No order placement.

The module converts candles, aggressive trades and L2 state into a small,
testable feature contract for the later scoring/gating layer.

Definitions:
- sweep: current candle takes a prior swing extreme and closes back through it;
- FVG: three-candle imbalance using the standard high/low gap definition;
- CVD: cumulative aggressive buy volume minus aggressive sell volume;
- book imbalance: signed top-N resting depth imbalance.

All functions are side-effect free and use only supplied observations.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from math import isfinite, sqrt
from typing import Any, Iterable, Mapping, Sequence


@dataclass(frozen=True)
class SweepFeature:
    direction: str                 # LOW_SWEEP / HIGH_SWEEP / NONE
    level: float | None
    depth: float
    rejection: float
    displacement: float
    valid: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FVGFeature:
    direction: str                 # BULLISH / BEARISH / NONE
    low: float | None
    high: float | None
    midpoint: float | None
    size: float
    size_atr: float
    valid: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CVDFeature:
    cumulative: float
    delta: float
    delta_ratio: float
    slope: float
    buy_volume: float
    sell_volume: float
    known_volume: float
    buy_count: int
    sell_count: int
    valid: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ImbalanceFeature:
    levels: int
    bid_depth: float
    ask_depth: float
    imbalance: float
    spread: float | None
    spread_bps: float | None
    valid: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ScalpingFeatures:
    sweep: SweepFeature
    fvg: FVGFeature
    cvd: CVDFeature
    imbalance: ImbalanceFeature
    atr: float
    displacement_atr: float
    volume: float
    volume_z: float
    sweep_depth_atr: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "sweep": self.sweep.to_dict(),
            "fvg": self.fvg.to_dict(),
            "cvd": self.cvd.to_dict(),
            "imbalance": self.imbalance.to_dict(),
            "atr": self.atr,
            "displacement_atr": self.displacement_atr,
            "volume": self.volume,
            "volume_z": self.volume_z,
            "sweep_depth_atr": self.sweep_depth_atr,
        }


def _f(value: Any, default: float = 0.0) -> float:
    try:
        x = float(value)
        return x if isfinite(x) else default
    except (TypeError, ValueError):
        return default


def _side(trade: Mapping[str, Any]) -> str:
    side = str(trade.get("side", "")).lower()
    if side in {"buy", "sell"}:
        return side

    # Existing Delta convention in this repository.
    role = str(trade.get("role", "")).lower()
    if role in {"m", "sell"}:
        return "sell"
    if role in {"t", "buy"}:
        return "buy"

    return "unknown"


def true_ranges(candles: Sequence[Mapping[str, Any]]) -> list[float]:
    out: list[float] = []
    prev_close: float | None = None
    for candle in candles:
        high = _f(candle.get("high"))
        low = _f(candle.get("low"))
        close = _f(candle.get("close"))
        if high <= 0 or low <= 0 or high < low:
            continue
        if prev_close is None:
            tr = high - low
        else:
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        out.append(max(tr, 0.0))
        prev_close = close if close > 0 else prev_close
    return out


def atr(candles: Sequence[Mapping[str, Any]], period: int = 14) -> float:
    trs = true_ranges(candles)
    if not trs or period <= 0:
        return 0.0
    window = trs[-period:]
    return sum(window) / len(window)


def zscore(value: float, history: Sequence[float], min_samples: int = 20) -> float:
    """Population z-score; returns 0 until a stable reference exists."""
    values = [_f(x, float("nan")) for x in history]
    values = [x for x in values if isfinite(x)]
    if len(values) < min_samples:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / len(values)
    sd = sqrt(variance)
    return (value - mean) / sd if sd > 1e-12 else 0.0


def detect_sweep(
    candles: Sequence[Mapping[str, Any]],
    *,
    lookback: int = 20,
    atr_value: float | None = None,
    min_depth_atr: float = 0.0,
) -> SweepFeature:
    """Detect the latest closed-candle liquidity sweep.

    A low sweep requires low < prior lookback low and close > prior low.
    A high sweep requires high > prior lookback high and close < prior high.

    The current candle is excluded from the reference window to prevent
    look-ahead leakage.
    """
    rows = list(candles)
    if len(rows) < max(3, lookback + 1):
        return SweepFeature("NONE", None, 0.0, 0.0, 0.0, False)

    current = rows[-1]
    reference = rows[-(lookback + 1):-1]
    prior_low = min(_f(c.get("low")) for c in reference)
    prior_high = max(_f(c.get("high")) for c in reference)

    high = _f(current.get("high"))
    low = _f(current.get("low"))
    close = _f(current.get("close"))
    open_ = _f(current.get("open"))

    if high <= 0 or low <= 0 or close <= 0 or prior_low <= 0 or prior_high <= 0:
        return SweepFeature("NONE", None, 0.0, 0.0, 0.0, False)

    a = atr_value if atr_value is not None else atr(rows)
    a = max(a, 1e-12)
    candle_range = max(high - low, 1e-12)

    if low < prior_low and close > prior_low:
        depth = prior_low - low
        rejection = (close - low) / candle_range
        displacement = abs(close - open_) / a
        valid = depth / a >= min_depth_atr
        return SweepFeature("LOW_SWEEP", prior_low, depth, rejection, displacement, valid)

    if high > prior_high and close < prior_high:
        depth = high - prior_high
        rejection = (high - close) / candle_range
        displacement = abs(close - open_) / a
        valid = depth / a >= min_depth_atr
        return SweepFeature("HIGH_SWEEP", prior_high, depth, rejection, displacement, valid)

    return SweepFeature("NONE", None, 0.0, 0.0, 0.0, False)


def detect_fvg(
    candles: Sequence[Mapping[str, Any]],
    *,
    atr_value: float | None = None,
    min_size_atr: float = 0.0,
) -> FVGFeature:
    """Detect the newest three-candle fair-value gap.

    Bullish: current low > high two candles back.
    Bearish: current high < low two candles back.

    The gap is represented as [low, high] regardless of direction.
    """
    rows = list(candles)
    if len(rows) < 3:
        return FVGFeature("NONE", None, None, None, 0.0, 0.0, False)

    left = rows[-3]
    current = rows[-1]
    a = max(atr_value if atr_value is not None else atr(rows), 1e-12)

    left_high = _f(left.get("high"))
    left_low = _f(left.get("low"))
    current_high = _f(current.get("high"))
    current_low = _f(current.get("low"))

    if min(left_high, left_low, current_high, current_low) <= 0:
        return FVGFeature("NONE", None, None, None, 0.0, 0.0, False)

    if current_low > left_high:
        gap_low, gap_high = left_high, current_low
        size = gap_high - gap_low
        size_atr = size / a
        return FVGFeature(
            "BULLISH", gap_low, gap_high, (gap_low + gap_high) / 2.0,
            size, size_atr, size_atr >= min_size_atr,
        )

    if current_high < left_low:
        gap_low, gap_high = current_high, left_low
        size = gap_high - gap_low
        size_atr = size / a
        return FVGFeature(
            "BEARISH", gap_low, gap_high, (gap_low + gap_high) / 2.0,
            size, size_atr, size_atr >= min_size_atr,
        )

    return FVGFeature("NONE", None, None, None, 0.0, 0.0, False)


def compute_cvd(
    trades: Iterable[Mapping[str, Any]],
    *,
    prior_cvd: float = 0.0,
    slope_window: int = 10,
) -> CVDFeature:
    rows = list(trades)
    buy_volume = 0.0
    sell_volume = 0.0
    buy_count = 0
    sell_count = 0

    deltas: list[float] = []
    for trade in rows:
        size = abs(_f(trade.get("size", trade.get("s"))))
        side = _side(trade)
        if size <= 0 or side == "unknown":
            continue
        delta = size if side == "buy" else -size
        deltas.append(delta)
        if side == "buy":
            buy_volume += size
            buy_count += 1
        else:
            sell_volume += size
            sell_count += 1

    known = buy_volume + sell_volume
    delta = buy_volume - sell_volume
    ratio = delta / known if known > 0 else 0.0
    cumulative = prior_cvd + delta

    if not deltas:
        slope = 0.0
    else:
        slope = sum(deltas[-max(1, slope_window):])

    return CVDFeature(
        cumulative=cumulative,
        delta=delta,
        delta_ratio=ratio,
        slope=slope,
        buy_volume=buy_volume,
        sell_volume=sell_volume,
        known_volume=known,
        buy_count=buy_count,
        sell_count=sell_count,
        valid=known > 0,
    )


def book_imbalance(
    order_book: Mapping[str, Any],
    *,
    levels: int = 5,
) -> ImbalanceFeature:
    """Calculate signed resting-depth imbalance from either live-state schema.

    Supports:
      1. pre-aggregated bid_depth_N / ask_depth_N;
      2. raw bids/asks as {price: size} or [(price, size)].
    """
    levels = max(1, int(levels))
    bid_key = f"bid_depth_{levels}"
    ask_key = f"ask_depth_{levels}"

    bid_depth = _f(order_book.get(bid_key), float("nan"))
    ask_depth = _f(order_book.get(ask_key), float("nan"))

    if not (isfinite(bid_depth) and isfinite(ask_depth)):
        raw_bids = order_book.get("bids", {})
        raw_asks = order_book.get("asks", {})
        if isinstance(raw_bids, Mapping):
            bids = sorted(
                ((_f(p), _f(q)) for p, q in raw_bids.items() if _f(q) > 0),
                key=lambda x: x[0],
                reverse=True,
            )[:levels]
        else:
            bids = sorted(
                ((_f(p), _f(q)) for p, q in raw_bids if _f(q) > 0),
                key=lambda x: x[0],
                reverse=True,
            )[:levels]

        if isinstance(raw_asks, Mapping):
            asks = sorted(
                ((_f(p), _f(q)) for p, q in raw_asks.items() if _f(q) > 0),
                key=lambda x: x[0],
            )[:levels]
        else:
            asks = sorted(
                ((_f(p), _f(q)) for p, q in raw_asks if _f(q) > 0),
                key=lambda x: x[0],
            )[:levels]

        bid_depth = sum(q for _, q in bids)
        ask_depth = sum(q for _, q in asks)

    total = bid_depth + ask_depth
    signed = (bid_depth - ask_depth) / total if total > 0 else 0.0

    bid = _f(order_book.get("best_bid"))
    ask = _f(order_book.get("best_ask"))
    if bid <= 0 or ask <= 0:
        bid = _f(order_book.get("bid"))
        ask = _f(order_book.get("ask"))

    spread = ask - bid if bid > 0 and ask > 0 and ask >= bid else None
    mid = (ask + bid) / 2.0 if spread is not None else None
    spread_bps = spread / mid * 10000.0 if spread is not None and mid else None

    return ImbalanceFeature(
        levels=levels,
        bid_depth=bid_depth,
        ask_depth=ask_depth,
        imbalance=signed,
        spread=spread,
        spread_bps=spread_bps,
        valid=total > 0,
    )


def build_features(
    candles: Sequence[Mapping[str, Any]],
    trades: Iterable[Mapping[str, Any]],
    order_book: Mapping[str, Any],
    *,
    prior_cvd: float = 0.0,
    lookback: int = 20,
    atr_period: int = 14,
    imbalance_levels: int = 5,
    volume_history: Sequence[float] = (),
) -> ScalpingFeatures:
    rows = list(candles)
    a = atr(rows, atr_period)
    last_volume = _f(rows[-1].get("volume")) if rows else 0.0
    sweep = detect_sweep(rows, lookback=lookback, atr_value=a)
    fvg = detect_fvg(rows, atr_value=a)
    cvd = compute_cvd(trades, prior_cvd=prior_cvd)
    imbalance = book_imbalance(order_book, levels=imbalance_levels)

    candle_range = 0.0
    if rows:
        candle_range = max(_f(rows[-1].get("high")) - _f(rows[-1].get("low")), 0.0)
    displacement_atr = candle_range / max(a, 1e-12)
    history = list(volume_history)
    volume_z = zscore(last_volume, history) if history else 0.0

    return ScalpingFeatures(
        sweep=sweep,
        fvg=fvg,
        cvd=cvd,
        imbalance=imbalance,
        atr=a,
        displacement_atr=displacement_atr,
        volume=last_volume,
        volume_z=volume_z,
        sweep_depth_atr=sweep.depth / max(a, 1e-12) if a > 0 else 0.0,
    )
