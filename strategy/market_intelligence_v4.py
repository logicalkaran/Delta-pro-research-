"""V4 market-intelligence feature layer.

Research only. No orders. Produces normalized features from the existing
microstructure state and a session gate. Cross-venue fields are optional and
remain neutral until real multi-venue data is connected.
"""
from dataclasses import dataclass
from strategy.timezone_gate import session_state

@dataclass(frozen=True)
class V4Config:
    min_fresh: float = 2.0
    min_trades_5: int = 4
    min_spread_bps: float = 0.0
    max_spread_bps: float = 5.0

def _f(x, d=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return d

def features(state, cfg=V4Config()):
    w5 = state["windows"]["5"]
    w30 = state["windows"]["30"]
    w60 = state["windows"]["60"]
    p5 = state["price"]["5"]
    ob = state["order_book"]
    q = state["quality"]
    mid = max(_f(ob.get("mid_price")), 1e-9)
    spread_bps = _f(ob.get("spread")) / mid * 10000.0
    buy5 = _f(w5.get("buy_volume"))
    sell5 = _f(w5.get("sell_volume"))
    total5 = max(buy5 + sell5, 1e-9)
    buy30 = _f(w30.get("buy_volume"))
    sell30 = _f(w30.get("sell_volume"))
    total30 = max(buy30 + sell30, 1e-9)
    delta5 = _f(w5.get("delta_pct"))
    delta30 = _f(w30.get("delta_pct"))
    delta60 = _f(w60.get("delta_pct"))
    imb = _f(ob.get("imbalance_5"))
    cvd_slope = _f(state.get("cvd_slope_30s"))
    pressure = (buy5 - sell5) / total5
    flow_accel = delta5 - delta30
    depth = max(_f(ob.get("bid_depth_5")) + _f(ob.get("ask_depth_5")), 1e-9)
    depth_skew = (_f(ob.get("bid_depth_5")) - _f(ob.get("ask_depth_5"))) / depth
    trade_rate_5 = _f(w5.get("trades")) / 5.0
    trade_rate_30 = _f(w30.get("trades")) / 30.0
    activity_accel = trade_rate_5 / max(trade_rate_30, 1e-9)
    mom = _f(p5.get("return_pct"))
    sess = session_state(state.get("timestamp"))
    quality_ok = _f(q.get("fresh_seconds"), 999) <= cfg.min_fresh and w5.get("trades", 0) >= cfg.min_trades_5 and cfg.min_spread_bps <= spread_bps <= cfg.max_spread_bps
    return {
        "quality_ok": quality_ok,
        "session": sess["session"],
        "session_allowed": sess["allowed"],
        "utc_hour": sess["utc_hour"],
        "spread_bps": spread_bps,
        "delta5": delta5,
        "delta30": delta30,
        "delta60": delta60,
        "delta_alignment": (delta5 + delta30 + delta60) / 3.0,
        "flow_acceleration": flow_accel,
        "cvd_slope_30s": cvd_slope,
        "book_imbalance": imb,
        "depth_skew": depth_skew,
        "trade_rate_acceleration": activity_accel,
        "aggression_pressure": pressure,
        "momentum_5": mom,
    }

def score(f):
    if not f["quality_ok"] or not f["session_allowed"]:
        return {"action": "NO_TRADE", "score": 0.0, "reason": "QUALITY_OR_SESSION_BLOCK"}
    long_score = 0.0
    short_score = 0.0
    long_score += 2.0 if f["delta5"] > 0.12 else 0.0
    long_score += 1.5 if f["delta30"] > 0.08 else 0.0
    long_score += 1.0 if f["delta60"] > 0.0 else 0.0
    long_score += 1.5 if f["book_imbalance"] > 0.12 else 0.0
    long_score += 1.0 if f["momentum_5"] > 0.025 else 0.0
    long_score += 1.0 if f["flow_acceleration"] > 0.02 else 0.0
    long_score += 1.0 if f["depth_skew"] > 0.10 else 0.0
    short_score += 2.0 if f["delta5"] < -0.12 else 0.0
    short_score += 1.5 if f["delta30"] < -0.08 else 0.0
    short_score += 1.0 if f["delta60"] < 0.0 else 0.0
    short_score += 1.5 if f["book_imbalance"] < -0.12 else 0.0
    short_score += 1.0 if f["momentum_5"] < -0.025 else 0.0
    short_score += 1.0 if f["flow_acceleration"] < -0.02 else 0.0
    short_score += 1.0 if f["depth_skew"] < -0.10 else 0.0
    if max(long_score, short_score) < 6.0:
        return {"action": "NO_TRADE", "score": max(long_score, short_score), "reason": "EDGE_THRESHOLD"}
    if long_score > short_score:
        return {"action": "LONG", "score": long_score, "reason": "MULTI_FACTOR_ALIGNMENT"}
    return {"action": "SHORT", "score": short_score, "reason": "MULTI_FACTOR_ALIGNMENT"}
