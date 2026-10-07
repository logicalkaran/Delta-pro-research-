"""Microstructure Scalper V2 research-only filter.
Adds cost-aware minimum edge and stronger multi-factor alignment.
Never places or modifies orders.
"""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class V2Config:
    min_score: int = 7
    min_delta_pct_5: float = 0.12
    min_delta_pct_30: float = 0.08
    min_imbalance_5: float = 0.12
    min_momentum_pct_5: float = 0.025
    min_trades_5: int = 3
    max_spread_bps: float = 5.0
    max_fresh_seconds: float = 2.0
    min_expected_move_pct: float = 0.12
    cost_buffer_pct: float = 0.05

@dataclass(frozen=True)
class Signal:
    action: str
    score: int
    confidence: float
    reasons: tuple[str,...]
    expected_move_pct: float

def _f(x, d=0.0):
    try: return float(x)
    except (TypeError,ValueError): return d

def evaluate(state, cfg=V2Config()):
    w5=state.get("windows",{}).get("5",{})
    w30=state.get("windows",{}).get("30",{})
    ob=state.get("order_book",{})
    px=state.get("price",{}).get("5",{})
    q=state.get("quality",{})
    delta5=_f(w5.get("delta_pct")); delta30=_f(w30.get("delta_pct"))
    imb=_f(ob.get("imbalance_5")); mom=_f(px.get("return_pct"))
    trades=int(_f(w5.get("trades")))
    spread=_f(ob.get("spread")); mid=_f(ob.get("mid_price"))
    fresh=_f(q.get("fresh_seconds"),999)
    spread_bps=(spread/mid*10000) if mid>0 else 999
    if trades<cfg.min_trades_5 or fresh>cfg.max_fresh_seconds or spread_bps>cfg.max_spread_bps:
        return Signal("NO_TRADE",0,0.0,("QUALITY_BLOCK",),0.0)
    score=0; reasons=[]
    if delta5>=cfg.min_delta_pct_5: score+=3; reasons.append("DELTA_5_STRONG")
    elif delta5<=-cfg.min_delta_pct_5: score-=3; reasons.append("DELTA_5_STRONG")
    if delta30>=cfg.min_delta_pct_30: score+=2; reasons.append("DELTA_30_CONFIRM")
    elif delta30<=-cfg.min_delta_pct_30: score-=2; reasons.append("DELTA_30_CONFIRM")
    if imb>=cfg.min_imbalance_5: score+=2; reasons.append("BOOK_IMBALANCE_BULL")
    elif imb<=-cfg.min_imbalance_5: score-=2; reasons.append("BOOK_IMBALANCE_BEAR")
    if mom>=cfg.min_momentum_pct_5: score+=2; reasons.append("MOMENTUM_BULL")
    elif mom<=-cfg.min_momentum_pct_5: score-=2; reasons.append("MOMENTUM_BEAR")
    same_long=delta5>0 and delta30>0 and imb>0 and mom>0
    same_short=delta5<0 and delta30<0 and imb<0 and mom<0
    if same_long: score+=1; reasons.append("FULL_ALIGNMENT")
    if same_short: score-=1; reasons.append("FULL_ALIGNMENT")
    expected=abs(mom)+abs(delta5)*0.15+abs(imb)*0.10
    if expected < cfg.min_expected_move_pct+cfg.cost_buffer_pct:
        return Signal("NO_TRADE",score,0.0,tuple(reasons+["EDGE_TOO_SMALL"]),expected)
    if score>=cfg.min_score and same_long:
        return Signal("LONG",score,min(0.99,0.5+score*0.05),tuple(reasons),expected)
    if score<=-cfg.min_score and same_short:
        return Signal("SHORT",score,min(0.99,0.5+abs(score)*0.05),tuple(reasons),expected)
    return Signal("NO_TRADE",score,0.0,tuple(reasons),expected)
