"""Confluence-based 1m/5m BTC directional scalper decision engine.

Research/shadow/paper only. This module never submits, cancels, or modifies orders.
It combines the existing short-horizon forecast with closed-candle trend, CVD,
order-book imbalance, spread/data-quality gates, and a symmetric 1:1 plan.
Forecast movement is a heuristic estimate until calibrated on unseen sessions.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite
import time
from typing import Any, Mapping, Sequence

from strategy.predictive_levels_v1 import compute_levels
from strategy.short_horizon_predictor_v1 import predict

@dataclass(frozen=True)
class ConfluenceConfig:
    min_confluence: int = 4
    min_probability: float = 0.60
    min_forecast_confidence: float = 0.55
    max_fresh_seconds: float = 2.0
    max_spread_bps: float = 5.0
    min_atr_fraction: float = 0.00015
    max_atr_fraction: float = 0.02
    stop_atr_multiple: float = 0.80
    round_trip_cost_bps: float = 15.8
    min_move_to_cost_multiple: float = 1.5
    min_book_imbalance: float = 0.10
    min_cvd_delta_ratio: float = 0.08
    min_expected_net_bps: float = 2.0


def _f(v: Any, default: float = 0.0) -> float:
    try:
        x = float(v)
        return x if isfinite(x) else default
    except (TypeError, ValueError):
        return default


def _ema(values: Sequence[float], period: int) -> float:
    if not values:
        return 0.0
    alpha = 2.0 / (period + 1.0)
    value = values[0]
    for x in values[1:]:
        value = alpha * x + (1.0 - alpha) * value
    return value


def _closed_rows(candles: Sequence[Mapping[str, Any]]) -> list[dict[str, float]]:
    rows = []
    for c in candles:
        o, h, l, close = (_f(c.get(k)) for k in ("open", "high", "low", "close"))
        volume = max(0.0, _f(c.get("volume")))
        if min(o, h, l, close) > 0 and h >= max(o, close, l) and l <= min(o, close, h):
            rows.append({"open": o, "high": h, "low": l, "close": close, "volume": volume})
    return rows


def _trend(candles: Sequence[Mapping[str, Any]]) -> str:
    rows = _closed_rows(candles)
    if len(rows) < 30:
        return "UNKNOWN"
    closes = [x["close"] for x in rows]
    fast = _ema(closes[-60:], 8)
    slow = _ema(closes[-120:], 21)
    last = closes[-1]
    if last > fast > slow:
        return "LONG"
    if last < fast < slow:
        return "SHORT"
    return "FLAT"


def evaluate(candles_1m: Sequence[Mapping[str, Any]],
             candles_5m: Sequence[Mapping[str, Any]],
             state: Mapping[str, Any],
             config: ConfluenceConfig = ConfluenceConfig()) -> dict[str, Any]:
    """Return a directional decision and 1:1 plan; abstain on any hard-gate failure.

    Caller must pass completed candles only. The function does not place orders.
    """
    rejected: list[str] = []
    evidence: list[str] = []
    book = state.get("order_book", {}) if isinstance(state, Mapping) else {}
    quality = state.get("quality", {}) if isinstance(state, Mapping) else {}
    windows = state.get("windows", {}) if isinstance(state, Mapping) else {}
    price = _f(book.get("mid_price"))
    if price <= 0:
        return _abstain("INVALID_OR_MISSING_PRICE", rejected, evidence)
    if len(_closed_rows(candles_1m)) < 60:
        rejected.append("INSUFFICIENT_1M_HISTORY")
    if len(_closed_rows(candles_5m)) < 30:
        rejected.append("INSUFFICIENT_5M_HISTORY")
    fresh = _f(quality.get("fresh_seconds"), 1e9)
    state_epoch = _f(state.get("updated_at_epoch", state.get("timestamp")), 0.0)
    state_age = time.time() - state_epoch if state_epoch > 0 else float("inf")
    if fresh > config.max_fresh_seconds or state_age < -5 or state_age > config.max_fresh_seconds:
        rejected.append("STALE_MARKET_DATA")
    bid, ask = _f(book.get("best_bid")), _f(book.get("best_ask"))
    if bid <= 0 or ask < bid or ask <= 0:
        rejected.append("INVALID_BOOK")
        spread_bps = None
    else:
        spread_bps = (ask - bid) / price * 10000.0
        if spread_bps > config.max_spread_bps:
            rejected.append("SPREAD_TOO_WIDE")
    if rejected:
        return _abstain(rejected[0], rejected, evidence, price=price, spread_bps=spread_bps)

    rows1 = _closed_rows(candles_1m)
    levels = compute_levels(rows1, price, dict(book))
    forecast = predict(rows1, levels, dict(state))
    forecasts = [x for x in forecast.forecasts if 1 <= int(x.minutes) <= 5]
    if not forecasts:
        return _abstain("NO_FORECAST", ["NO_FORECAST"], evidence, price=price, spread_bps=spread_bps)
    # Choose the horizon with the largest conservative directional forecast, not the largest raw score.
    chosen = max(forecasts, key=lambda x: abs(_f(x.expected_return_pct)))
    p_up = _f(chosen.probability_up, 0.5)
    forecast_side = "LONG" if p_up >= config.min_probability else "SHORT" if p_up <= 1.0-config.min_probability else "FLAT"
    forecast_move_bps = _f(chosen.expected_return_pct) * 100.0
    forecast_conf = _f(chosen.confidence)
    if forecast_side == "FLAT":
        return _abstain("FORECAST_NOT_DIRECTIONAL", ["FORECAST_NOT_DIRECTIONAL"], evidence,
                        price=price, spread_bps=spread_bps, forecast=asdict(chosen))
    if forecast_conf < config.min_forecast_confidence:
        return _abstain("FORECAST_CONFIDENCE_TOO_LOW", ["FORECAST_CONFIDENCE_TOO_LOW"], evidence,
                        price=price, spread_bps=spread_bps, forecast=asdict(chosen))
    if (forecast_side == "LONG" and forecast_move_bps <= 0) or (forecast_side == "SHORT" and forecast_move_bps >= 0):
        return _abstain("FORECAST_SIGN_CONFLICT", ["FORECAST_SIGN_CONFLICT"], evidence,
                        price=price, spread_bps=spread_bps, forecast=asdict(chosen))

    trend1 = _trend(rows1)
    trend5 = _trend(candles_5m)
    d5 = _f(windows.get("5", {}).get("delta_pct"))
    d30 = _f(windows.get("30", {}).get("delta_pct"))
    cvd_slope = _f(state.get("cvd_slope_30s"))
    cvd_aligned = ((d5 >= config.min_cvd_delta_ratio or d30 >= config.min_cvd_delta_ratio or cvd_slope > 0)
                   if forecast_side == "LONG" else
                   (d5 <= -config.min_cvd_delta_ratio or d30 <= -config.min_cvd_delta_ratio or cvd_slope < 0))
    imbalance = _f(book.get("imbalance_5"))
    book_aligned = imbalance >= config.min_book_imbalance if forecast_side == "LONG" else imbalance <= -config.min_book_imbalance
    trend1_aligned = trend1 == forecast_side
    trend5_aligned = trend5 == forecast_side
    regime = str(state.get("regime", "UNKNOWN")).upper()
    absorption_aligned = (forecast_side == "LONG" and "BUYER_ABSORPTION" in regime) or (forecast_side == "SHORT" and "SELLER_ABSORPTION" in regime)

    votes = {
        "FORECAST": True,
        "1M_TREND": trend1_aligned,
        "5M_TREND": trend5_aligned,
        "CVD_FLOW": cvd_aligned,
        "ORDERBOOK_IMBALANCE": book_aligned,
    }
    evidence.extend(k for k, ok in votes.items() if ok)
    conflicts = [k for k, ok in (("1M_TREND", trend1), ("5M_TREND", trend5)) if ok not in (forecast_side, "FLAT", "UNKNOWN")]
    if conflicts:
        return _abstain("HIGHER_SIGNAL_CONFLICT", ["HIGHER_SIGNAL_CONFLICT"], evidence,
                        price=price, spread_bps=spread_bps, votes=votes, forecast=asdict(chosen))
    if not cvd_aligned:
        rejected.append("CVD_NOT_CONFIRMED")
    if not book_aligned:
        rejected.append("ORDERBOOK_NOT_CONFIRMED")
    confluence = sum(bool(x) for x in votes.values())
    if confluence < config.min_confluence:
        rejected.append("INSUFFICIENT_CONFLUENCE")

    atr_value = _f(levels.atr)
    atr_fraction = atr_value / price if price else 0.0
    if atr_value <= 0 or not config.min_atr_fraction <= atr_fraction <= config.max_atr_fraction:
        rejected.append("ATR_OUT_OF_RANGE")
    risk_distance = max(atr_value * config.stop_atr_multiple, price * 0.0001)
    risk_bps = risk_distance / price * 10000.0
    expected_abs_bps = abs(forecast_move_bps)
    expected_net_bps = expected_abs_bps - config.round_trip_cost_bps
    if expected_abs_bps < risk_bps + config.round_trip_cost_bps * config.min_move_to_cost_multiple:
        rejected.append("FORECAST_MOVE_INSUFFICIENT_FOR_TARGET_AND_COSTS")
    if expected_net_bps < config.min_expected_net_bps:
        rejected.append("EXPECTED_NET_EDGE_TOO_LOW")

    stop = price - risk_distance if forecast_side == "LONG" else price + risk_distance
    target = price + risk_distance if forecast_side == "LONG" else price - risk_distance
    allowed = not rejected
    return {
        "schema": "confluence_1m5m_v1_decision",
        "decision": forecast_side if allowed else "NO_TRADE",
        "side": forecast_side,
        "allowed": allowed,
        "paper_only": True,
        "real_orders": False,
        "live_execution_enabled": False,
        "entry_reference": round(price, 8),
        "stop": round(stop, 8),
        "target": round(target, 8),
        "reward_to_risk": 1.0,
        "forecast_horizon_minutes": int(chosen.minutes),
        "forecast_direction": chosen.direction,
        "forecast_probability_up": p_up,
        "forecast_confidence": forecast_conf,
        "forecast_expected_move_bps": round(forecast_move_bps, 4),
        "expected_move_is_calibrated": False,
        "estimated_round_trip_cost_bps": config.round_trip_cost_bps,
        "estimated_net_move_bps": round(expected_net_bps, 4),
        "risk_distance_bps": round(risk_bps, 4),
        "confluence_votes": confluence,
        "confluence_required": config.min_confluence,
        "signals": {**votes, "ABSORPTION_CONTEXT": absorption_aligned},
        "trends": {"1m": trend1, "5m": trend5},
        "market_regime": regime,
        "spread_bps": round(spread_bps, 4) if spread_bps is not None else None,
        "data_fresh_seconds": fresh,
        "state_age_seconds": round(state_age, 4) if isfinite(state_age) else None,
        "evidence": evidence,
        "rejected": rejected,
        "reason": "CONFLUENCE_CONFIRMED" if allowed else rejected[0],
    }


def _abstain(reason: str, rejected: list[str], evidence: list[str], **extra: Any) -> dict[str, Any]:
    return {"schema": "confluence_1m5m_v1_decision", "decision": "NO_TRADE", "side": None,
            "allowed": False, "paper_only": True, "real_orders": False,
            "live_execution_enabled": False, "reward_to_risk": 1.0,
            "expected_move_is_calibrated": False, "reason": reason,
            "evidence": evidence, "rejected": rejected, **extra}

if __name__ == "__main__":
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    candle_path = root / "data/processed/live_multi_timeframe_candles_v1.json"
    state_path = root / "data/live_microstructure_state.json"
    try:
        payload = json.loads(candle_path.read_text())
        state = json.loads(state_path.read_text())
        frames = payload.get("candles", {})
        result = evaluate(frames.get("1m", []), frames.get("5m", []), state)
    except Exception as exc:
        result = _abstain("INPUT_LOAD_FAILED", [type(exc).__name__], [])
    print(json.dumps(result, indent=2, allow_nan=False))
