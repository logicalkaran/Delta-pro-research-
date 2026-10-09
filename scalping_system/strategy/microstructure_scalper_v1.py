"""Research-only BTC microstructure scalping signal engine.

Consumes the existing read-only live_microstructure_state.json schema.
Produces LONG/SHORT/NO_TRADE proposals only. Never places or modifies orders.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class ScalperConfig:
    min_score: int = 6
    max_spread_bps: float = 5.0
    max_fresh_seconds: float = 2.0
    min_trades_5s: int = 3
    delta_strong: float = 0.20
    delta_confirm: float = 0.08
    imbalance_strong: float = 0.20
    imbalance_confirm: float = 0.10
    momentum_confirm_pct: float = 0.02
    momentum_strong_pct: float = 0.05


@dataclass(frozen=True)
class ScalpSignal:
    action: str
    score: int
    confidence: float
    regime: str
    reasons: tuple[str, ...]
    blocked: tuple[str, ...]


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _i(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _spread_bps(book: Mapping[str, Any]) -> float:
    mid = _f(book.get("mid_price"))
    spread = _f(book.get("spread"))
    return spread / mid * 10_000.0 if mid > 0 else float("inf")


def evaluate(state: Mapping[str, Any], cfg: ScalperConfig = ScalperConfig()) -> ScalpSignal:
    """Evaluate one microstructure snapshot without side effects."""
    windows = state.get("windows") or {}
    prices = state.get("price") or {}
    book = state.get("order_book") or {}
    quality = state.get("quality") or {}

    w5 = windows.get("5") or {}
    w30 = windows.get("30") or {}
    p5 = (prices.get("5") or {})
    spread_bps = _spread_bps(book)
    fresh = _f(quality.get("fresh_seconds"), float("inf"))
    trades5 = _i(w5.get("trades"))
    delta = _f(w5.get("delta_pct"))
    delta30 = _f(w30.get("delta_pct"))
    obi = _f(book.get("imbalance_5"))
    obi10 = _f(book.get("imbalance_10"))
    ret5 = _f(p5.get("return_pct"))
    regime = str(state.get("regime") or "UNKNOWN")

    blocked = []
    if fresh > cfg.max_fresh_seconds:
        blocked.append("STALE_MICROSTRUCTURE")
    if spread_bps > cfg.max_spread_bps:
        blocked.append("WIDE_SPREAD")
    if trades5 < cfg.min_trades_5s:
        blocked.append("LOW_TRADE_SAMPLE")

    if blocked:
        return ScalpSignal("NO_TRADE", 0, 0.0, regime, (), tuple(blocked))

    score = 0
    reasons: list[str] = []

    # Aggressive-flow confirmation.
    if delta >= cfg.delta_strong:
        score += 3
        reasons.append("STRONG_BUY_DELTA")
    elif delta >= cfg.delta_confirm:
        score += 1
        reasons.append("BUY_DELTA_CONFIRM")
    elif delta <= -cfg.delta_strong:
        score -= 3
        reasons.append("STRONG_SELL_DELTA")
    elif delta <= -cfg.delta_confirm:
        score -= 1
        reasons.append("SELL_DELTA_CONFIRM")

    # Short-horizon price action must agree with flow.
    if ret5 >= cfg.momentum_strong_pct:
        score += 2
        reasons.append("PRICE_MOMENTUM_UP")
    elif ret5 >= cfg.momentum_confirm_pct:
        score += 1
        reasons.append("PRICE_CONFIRM_UP")
    elif ret5 <= -cfg.momentum_strong_pct:
        score -= 2
        reasons.append("PRICE_MOMENTUM_DOWN")
    elif ret5 <= -cfg.momentum_confirm_pct:
        score -= 1
        reasons.append("PRICE_CONFIRM_DOWN")

    # L2 liquidity pressure.
    if obi >= cfg.imbalance_strong:
        score += 2
        reasons.append("BID_LIQUIDITY_DOMINANT")
    elif obi >= cfg.imbalance_confirm:
        score += 1
        reasons.append("BID_IMBALANCE")
    elif obi <= -cfg.imbalance_strong:
        score -= 2
        reasons.append("ASK_LIQUIDITY_DOMINANT")
    elif obi <= -cfg.imbalance_confirm:
        score -= 1
        reasons.append("ASK_IMBALANCE")

    # Multi-window consistency reduces one-tick noise.
    if delta > cfg.delta_confirm and delta30 > 0:
        score += 1
        reasons.append("DELTA_MULTIWINDOW_UP")
    elif delta < -cfg.delta_confirm and delta30 < 0:
        score -= 1
        reasons.append("DELTA_MULTIWINDOW_DOWN")

    # L1/L2 agreement is a small additional confirmation.
    if obi > cfg.imbalance_confirm and obi10 > 0:
        score += 1
        reasons.append("DEPTH_CONFIRM_UP")
    elif obi < -cfg.imbalance_confirm and obi10 < 0:
        score -= 1
        reasons.append("DEPTH_CONFIRM_DOWN")

    if score >= cfg.min_score:
        action = "LONG"
    elif score <= -cfg.min_score:
        action = "SHORT"
    else:
        action = "NO_TRADE"

    confidence = min(1.0, abs(score) / float(cfg.min_score + 4))
    return ScalpSignal(action, score, round(confidence, 4), regime, tuple(reasons), ())


def evaluate_json_state(state: Mapping[str, Any], cfg: ScalperConfig = ScalperConfig()) -> dict[str, Any]:
    """JSON-friendly adapter for paper/research consumers."""
    s = evaluate(state, cfg)
    return {
        "strategy": "microstructure_scalper_v1",
        "read_only": True,
        "action": s.action,
        "score": s.score,
        "confidence": s.confidence,
        "regime": s.regime,
        "reasons": list(s.reasons),
        "blocked": list(s.blocked),
    }
