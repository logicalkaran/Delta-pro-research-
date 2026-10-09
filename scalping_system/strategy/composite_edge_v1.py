"""Composite short-horizon BTC edge selector. Research/paper only.

Combines market structure, CVD/flow, liquidity sweep, order-book imbalance,
predictive support/resistance and the existing 1-5m forecast. It does not
place orders and is not a live-trading authorization layer.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
import json, math

from strategy.predictive_levels_v1 import compute_levels
from strategy.short_horizon_predictor_v1 import predict

@dataclass(frozen=True)
class CompositeSignal:
    side: str
    score: float
    confidence: float
    entry: float
    stop: float
    target: float
    rr: float
    horizon_min: int
    reasons: tuple[str, ...]
    support: float | None
    resistance: float | None
    sweep: bool
    paper_only: bool = True

    def to_dict(self):
        return asdict(self)

def _f(x, d=0.0):
    try: return float(x)
    except (TypeError, ValueError): return d

def _market_structure(candles):
    cs = candles[-30:-1] if len(candles) > 30 else candles[:-1]
    if len(cs) < 10: return "UNKNOWN", None, None
    highs = [(_f(c.get("high")), i) for i,c in enumerate(cs)]
    lows = [(_f(c.get("low")), i) for i,c in enumerate(cs)]
    hi = max(x[0] for x in highs); lo = min(x[0] for x in lows)
    mid = _f(cs[-1].get("close"))
    recent_hi = max(_f(c.get("high")) for c in cs[-8:])
    recent_lo = min(_f(c.get("low")) for c in cs[-8:])
    if mid > recent_hi: return "BREAKOUT_UP", lo, recent_hi
    if mid < recent_lo: return "BREAKOUT_DOWN", recent_lo, hi
    if mid >= (hi+lo)/2: return "BULLISH_RANGE", lo, hi
    return "BEARISH_RANGE", lo, hi

def _sweep(candles, price, d5, imb):
    cs = candles[-21:-1] if len(candles) > 21 else candles[:-1]
    if len(cs) < 10: return None
    hi=max(_f(c.get("high")) for c in cs); lo=min(_f(c.get("low")) for c in cs)
    # Price returning inside a recently swept extreme, with flow reversal.
    if price <= lo*1.00025 and d5 > .10 and imb > .05: return "LOW_SWEEP"
    if price >= hi*0.99975 and d5 < -.10 and imb < -.05: return "HIGH_SWEEP"
    return None

def select(candles, state, min_score=78.0, min_rr=1.8):
    ob=state.get("order_book", {})
    px=_f(ob.get("mid_price"))
    if px<=0 or len(candles)<30: return None
    d5=_f(state.get("windows",{}).get("5",{}).get("delta_pct"))
    d30=_f(state.get("windows",{}).get("30",{}).get("delta_pct"))
    imb=_f(ob.get("imbalance_5"))
    fresh=_f(state.get("quality",{}).get("fresh_seconds"),999)
    if fresh>2: return None

    levels=compute_levels(candles,px,ob)
    forecast=predict(candles,levels,state)
    structure,_,_= _market_structure(candles)
    sweep=_sweep(candles,px,d5,imb)
    atr=max(levels.atr,px*.0005)

    candidates=[]
    for fc in forecast.forecasts:
        if fc.minutes>5: continue
        side="LONG" if fc.direction=="UP" else "SHORT" if fc.direction=="DOWN" else None
        if not side: continue
        score=0.0; reasons=[]
        if fc.confidence>=.60: score+=18; reasons.append("FORECAST_CONFIRMED")
        if (side=="LONG" and d5>.10) or (side=="SHORT" and d5<-.10):
            score+=16; reasons.append("CVD_FLOW_ALIGNED")
        if (side=="LONG" and d30>0) or (side=="SHORT" and d30<0):
            score+=8; reasons.append("30S_FLOW_ALIGNED")
        if (side=="LONG" and imb>.10) or (side=="SHORT" and imb<-.10):
            score+=14; reasons.append("ORDERBOOK_ALIGNED")
        if (side=="LONG" and structure in ("BULLISH_RANGE","BREAKOUT_UP")) or (side=="SHORT" and structure in ("BEARISH_RANGE","BREAKOUT_DOWN")):
            score+=12; reasons.append("MARKET_STRUCTURE_ALIGNED")
        if sweep=="LOW_SWEEP" and side=="LONG":
            score+=18; reasons.append("LIQUIDITY_LOW_SWEEP")
        if sweep=="HIGH_SWEEP" and side=="SHORT":
            score+=18; reasons.append("LIQUIDITY_HIGH_SWEEP")
        level=levels.nearest_resistance if side=="LONG" else levels.nearest_support
        if level is None: continue
        if side=="LONG":
            stop=min(px-atr, levels.nearest_support or px-atr)
            risk=max(px-stop,atr*.55); target=max(level,px+2*risk)
        else:
            stop=max(px+atr, levels.nearest_resistance or px+atr)
            risk=max(stop-px,atr*.55); target=min(level,px-2*risk)
        reward=abs(target-px); rr=reward/max(risk,1e-9)
        if rr<min_rr: continue
        score += min(12.0, rr*3.0)
        confidence=min(.95, max(.05, score/100.0))
        if score>=min_score:
            candidates.append(CompositeSignal(side,round(score,2),round(confidence,3),px,round(stop,2),round(target,2),round(rr,2),fc.minutes,tuple(reasons),levels.nearest_support,levels.nearest_resistance,bool(sweep),True))
    return max(candidates,key=lambda x:(x.score,x.rr,x.horizon_min),default=None)

def snapshot(candles,state):
    s=select(candles,state)
    return s.to_dict() if s else None
