"""Auditable research decision layer. No order submission."""
from dataclasses import dataclass
from strategy.market_intelligence_v4 import features, score

@dataclass(frozen=True)
class DecisionConfig:
    min_score: float = 6.0
    max_spread_bps: float = 5.0
    max_fresh_seconds: float = 2.0

def evaluate(state, timeframes=None, cross=None, cfg=DecisionConfig()):
    f=features(state)
    base=score(f)
    reasons=[]
    vetoes=[]
    if f["delta_alignment"]>0.08: reasons.append("FLOW_BULLISH")
    elif f["delta_alignment"]<-0.08: reasons.append("FLOW_BEARISH")
    if f["book_imbalance"]>0.12: reasons.append("BOOK_BID_PRESSURE")
    elif f["book_imbalance"]<-0.12: reasons.append("BOOK_ASK_PRESSURE")
    if f["cvd_slope_30s"]>0: reasons.append("CVD_RISING")
    elif f["cvd_slope_30s"]<0: reasons.append("CVD_FALLING")
    if f["momentum_5"]>0.025: reasons.append("MOMENTUM_UP")
    elif f["momentum_5"]<-0.025: reasons.append("MOMENTUM_DOWN")
    if f["spread_bps"]>cfg.max_spread_bps: vetoes.append("SPREAD_TOO_WIDE")
    if f["spread_bps"]<0: vetoes.append("INVALID_SPREAD")
    if state.get("quality",{}).get("fresh_seconds",999)>cfg.max_fresh_seconds: vetoes.append("STALE_DATA")
    if not f["session_allowed"]: vetoes.append("SESSION_BLOCK")
    tf=timeframes or {}
    sigs=[tf.get(k,{}).get("signal","HOLD") for k in ("1m","5m","1h")]
    buys=sigs.count("BUY"); sells=sigs.count("SELL")
    if buys>=2: reasons.append("MTF_BULLISH")
    elif sells>=2: reasons.append("MTF_BEARISH")
    else: reasons.append("MTF_CONFLICT")
    ce=(cross or {}).get("state") or (cross or {}).get("edge_v42",{}).get("state")
    if ce=="DIVERGENCE": vetoes.append("CROSS_VENUE_DIVERGENCE")
    elif ce=="VENUE_CONFIRMATION": reasons.append("VENUE_CONFIRMATION")
    action=base["action"]
    if action=="LONG" and sells>=2: vetoes.append("MTF_OPPOSES_LONG")
    if action=="SHORT" and buys>=2: vetoes.append("MTF_OPPOSES_SHORT")
    if vetoes: action="NO_TRADE"
    score_value=round(float(base["score"]),2)
    confidence=min(100,round(50+score_value*6+len(reasons)*3-len(vetoes)*12))
    return {"action":action,"score":score_value,"confidence":confidence,"base_action":base["action"],"reasons":reasons,"vetoes":vetoes,"timeframes":sigs,"session":f["session"],"spread_bps":round(f["spread_bps"],3),"fresh_seconds":state.get("quality",{}).get("fresh_seconds"),"paper_only":True,"order_submission":False}
