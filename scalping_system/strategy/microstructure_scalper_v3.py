"""Microstructure Scalper V3 research-only signal engine.
Adds persistence, divergence/absorption proxies, volatility/regime and cost-aware quality.
Never places or modifies orders.
"""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class V3Config:
    min_score: int = 9
    min_trades_5: int = 4
    max_spread_bps: float = 5.0
    max_fresh_seconds: float = 2.0
    min_delta5: float = 0.12
    min_delta30: float = 0.08
    min_imbalance5: float = 0.12
    min_momentum5: float = 0.025
    min_expected_move_pct: float = 0.12
    cost_buffer_pct: float = 0.05
    min_persistence: float = 0.60
    max_volatility_pct: float = 0.30

@dataclass(frozen=True)
class Signal:
    action: str
    score: int
    confidence: float
    reasons: tuple[str,...]
    expected_move_pct: float
    quality: float

def _f(x,d=0.0):
    try: return float(x)
    except (TypeError,ValueError): return d

def evaluate(state, cfg=V3Config()):
    w5=state.get("windows",{}).get("5",{}); w30=state.get("windows",{}).get("30",{})
    ob=state.get("order_book",{}); px=state.get("price",{}).get("5",{}); q=state.get("quality",{})
    d5=_f(w5.get("delta_pct")); d30=_f(w30.get("delta_pct"))
    imb=_f(ob.get("imbalance_5")); mom=_f(px.get("return_pct"))
    trades=int(_f(w5.get("trades"))); spread=_f(ob.get("spread")); mid=_f(ob.get("mid_price"))
    fresh=_f(q.get("fresh_seconds"),999)
    spread_bps=spread/mid*10000 if mid>0 else 999
    if trades<cfg.min_trades_5 or fresh>cfg.max_fresh_seconds or spread_bps>cfg.max_spread_bps:
        return Signal("NO_TRADE",0,0.0,("QUALITY_BLOCK",),0.0,0.0)

    # Optional richer fields; replay falls back safely when unavailable.
    persist=_f(state.get("persistence",state.get("signals",{}).get("persistence",1.0)),1.0)
    vol=_f(state.get("volatility_pct",state.get("volatility",{}).get("pct",0.0)),0.0)
    cvd_acc=_f(state.get("cvd_acceleration",0.0))
    divergence=_f(state.get("delta_price_divergence",0.0))
    absorption=_f(state.get("absorption",0.0))

    score=0; reasons=[]
    long=(d5>=cfg.min_delta5 and d30>=cfg.min_delta30 and imb>=cfg.min_imbalance5 and mom>=cfg.min_momentum5)
    short=(d5<=-cfg.min_delta5 and d30<=-cfg.min_delta30 and imb<=-cfg.min_imbalance5 and mom<=-cfg.min_momentum5)

    if long:
        score+=7; reasons+=["FULL_ALIGNMENT"]
    elif short:
        score-=7; reasons+=["FULL_ALIGNMENT"]

    if persist>=cfg.min_persistence:
        score += 2 if d5>0 else -2 if d5<0 else 0
        reasons.append("PERSISTENCE_CONFIRM")
    if abs(cvd_acc)>=0.05:
        score += 1 if cvd_acc>0 else -1
        reasons.append("CVD_ACCELERATION")
    if abs(absorption)>=0.10:
        score += 2 if absorption>0 else -2
        reasons.append("ABSORPTION")
    if abs(divergence)>=0.10:
        # Divergence is a warning against continuation; do not reward it.
        if (long and divergence<0) or (short and divergence>0):
            score -= 2 if long else -2
            reasons.append("DIVERGENCE_RISK")
        else:
            reasons.append("DIVERGENCE")

    expected=abs(mom)+abs(d5)*0.15+abs(imb)*0.10
    if vol>cfg.max_volatility_pct:
        return Signal("NO_TRADE",score,0.0,tuple(reasons+["VOLATILITY_BLOCK"]),expected,0.0)
    if expected < cfg.min_expected_move_pct+cfg.cost_buffer_pct:
        return Signal("NO_TRADE",score,0.0,tuple(reasons+["EDGE_TOO_SMALL"]),expected,0.0)
    if not (long or short) or persist<cfg.min_persistence:
        return Signal("NO_TRADE",score,0.0,tuple(reasons+["ALIGNMENT_BLOCK"]),expected,0.0)
    if long and score>=cfg.min_score:
        return Signal("LONG",score,min(.99,.50+score*.04),tuple(reasons),expected,min(1,score/14))
    if short and score<=-cfg.min_score:
        return Signal("SHORT",score,min(.99,.50+abs(score)*.04),tuple(reasons),expected,min(1,abs(score)/14))
    return Signal("NO_TRADE",score,0.0,tuple(reasons+["SCORE_BLOCK"]),expected,0.0)
