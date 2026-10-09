"""Research-only composite setup ranker. Does not place orders."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from strategy.predictive_levels_v1 import compute_levels
from strategy.short_horizon_predictor_v1 import predict

COST_BPS=12.0
MIN_SCORE=82.0
MIN_RR=2.0
MIN_EDGE_BPS=15.0

@dataclass(frozen=True)
class RankedComposite:
    side:str; rank_score:float; confidence:float; entry:float; stop:float; target:float
    rr:float; horizon_min:int; expected_move_bps:float; expected_edge_bps:float
    regime:str; support:float|None; resistance:float|None; sweep:str|None
    reasons:tuple[str,...]; paper_only:bool=True
    def to_dict(self): return asdict(self)

def _f(x,d=0.0):
    try:return float(x)
    except (TypeError,ValueError):return d

def _structure(cs):
    x=cs[-30:-1] if len(cs)>30 else cs[:-1]
    if len(x)<10:return "UNKNOWN"
    hi=max(_f(c.get("high")) for c in x[-8:]); lo=min(_f(c.get("low")) for c in x[-8:]); px=_f(x[-1].get("close"))
    ah=max(_f(c.get("high")) for c in x); al=min(_f(c.get("low")) for c in x)
    if px>hi:return "BREAKOUT_UP"
    if px<lo:return "BREAKOUT_DOWN"
    return "BULLISH_RANGE" if px>=(ah+al)/2 else "BEARISH_RANGE"

def _sweep(cs,px,d5,imb):
    x=cs[-21:-1] if len(cs)>21 else cs[:-1]
    if len(x)<10:return None
    hi=max(_f(c.get("high")) for c in x); lo=min(_f(c.get("low")) for c in x)
    if px<=lo*1.00025 and d5>.10 and imb>.05:return "LOW_SWEEP"
    if px>=hi*.99975 and d5<-.10 and imb<-.05:return "HIGH_SWEEP"
    return None

def rank(candles,state):
    ob=state.get("order_book",{}); px=_f(ob.get("mid_price"))
    if px<=0 or len(candles)<30:return None
    if _f(state.get("quality",{}).get("fresh_seconds"),999)>2:return None
    d5=_f(state.get("windows",{}).get("5",{}).get("delta_pct")); d30=_f(state.get("windows",{}).get("30",{}).get("delta_pct")); imb=_f(ob.get("imbalance_5"))
    levels=compute_levels(candles,px,ob); forecast=predict(candles,levels,state); structure=_structure(candles); sweep=_sweep(candles,px,d5,imb)
    atr=max(levels.atr,px*.0005); regime="HIGH_VOL" if atr/px>=.012 else "LOW_VOL" if atr/px<=.0045 else "NORMAL_VOL"
    out=[]
    for fc in forecast.forecasts:
        side="LONG" if fc.direction=="UP" else "SHORT" if fc.direction=="DOWN" else None
        if not side or fc.minutes>5 or fc.confidence<.60:continue
        if side=="LONG":
            stop=min(px-atr,levels.nearest_support or px-atr); risk=max(px-stop,atr*.55); target=max(levels.nearest_resistance or px+2*risk,px+2*risk)
        else:
            stop=max(px+atr,levels.nearest_resistance or px+atr); risk=max(stop-px,atr*.55); target=min(levels.nearest_support or px-2*risk,px-2*risk)
        rr=abs(target-px)/max(risk,1e-9)
        if rr<MIN_RR:continue
        move=abs(fc.probability_up-.5)*2*fc.confidence*(atr/px)*10000; edge=move-COST_BPS
        if edge<MIN_EDGE_BPS:continue
        score=40*fc.confidence; reasons=["FORECAST_CONFIRMED"]
        if (side=="LONG" and d5>.10) or (side=="SHORT" and d5<-.10):score+=12; reasons.append("CVD_FLOW_ALIGNED")
        if (side=="LONG" and d30>0) or (side=="SHORT" and d30<0):score+=6; reasons.append("30S_FLOW_ALIGNED")
        if (side=="LONG" and imb>.10) or (side=="SHORT" and imb<-.10):score+=10; reasons.append("ORDERBOOK_ALIGNED")
        if (side=="LONG" and structure in ("BULLISH_RANGE","BREAKOUT_UP")) or (side=="SHORT" and structure in ("BEARISH_RANGE","BREAKOUT_DOWN")):score+=10; reasons.append("STRUCTURE_ALIGNED")
        if sweep=="LOW_SWEEP" and side=="LONG":score+=12; reasons.append("LOW_SWEEP")
        if sweep=="HIGH_SWEEP" and side=="SHORT":score+=12; reasons.append("HIGH_SWEEP")
        if score<MIN_SCORE:continue
        out.append(RankedComposite(side,round(score+min(8,edge/10),2),round(fc.confidence,3),px,round(stop,2),round(target,2),round(rr,2),fc.minutes,round(move,2),round(edge,2),regime,levels.nearest_support,levels.nearest_resistance,sweep,tuple(reasons)))
    return max(out,key=lambda x:(x.rank_score,x.expected_edge_bps,x.rr),default=None)
