"""Unified scalper strategy portfolio. PAPER/SHADOW ONLY."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable

@dataclass(frozen=True)
class Signal:
    strategy: str
    action: str
    score: float
    expected_move_bps: float
    reason: str

def f(x,d=0.0):
    try:return float(x)
    except (TypeError,ValueError):return d

def features(s):
    w=s.get("windows",{});p=s.get("price",{});ob=s.get("order_book",{})
    d5=f(w.get("5",{}).get("delta_pct"));d30=f(w.get("30",{}).get("delta_pct"));d60=f(w.get("60",{}).get("delta_pct"))
    r5=f(p.get("5",{}).get("return_pct"))*100;r30=f(p.get("30",{}).get("return_pct"))*100;r60=f(p.get("60",{}).get("return_pct"))*100
    imb5=f(ob.get("imbalance_5"));imb10=f(ob.get("imbalance_10"));bid=f(ob.get("bid_depth_5"));ask=f(ob.get("ask_depth_5"))
    mid=f(ob.get("mid_price"));spread=f(ob.get("spread"));spread_bps=spread/max(mid,1e-9)*10000
    return locals()

def sig(name,action,score,reason):
    if action not in ("LONG","SHORT"):return Signal(name,"NO_TRADE",0,0,reason)
    score=max(0,float(score));return Signal(name,action,score,score*3,reason)

def absorption(s):
    x=features(s)
    if x["d5"]<=-.10 and x["r30"]>-.40:return sig("ABSORPTION_REVERSAL","LONG",min(10,abs(x["d5"])*8+1),"sell pressure absorbed")
    if x["d5"]>=.10 and x["r30"]<.40:return sig("ABSORPTION_REVERSAL","SHORT",min(10,abs(x["d5"])*8+1),"buy pressure absorbed")
    return sig("ABSORPTION_REVERSAL","NO_TRADE",0,"no absorption")

def delta_divergence(s):
    x=features(s)
    if x["d5"]<-.12 and x["r5"]>=0:return sig("DELTA_DIVERGENCE","LONG",min(10,abs(x["d5"])*10+2),"negative delta without price decline")
    if x["d5"]>.12 and x["r5"]<=0:return sig("DELTA_DIVERGENCE","SHORT",min(10,abs(x["d5"])*10+2),"positive delta without price rise")
    return sig("DELTA_DIVERGENCE","NO_TRADE",0,"no divergence")

def orderbook_imbalance(s):
    x=features(s);z=x["imb5"]
    if z>.18:return sig("ORDERBOOK_IMBALANCE","LONG",min(10,z*20+2),"bid depth dominates")
    if z<-.18:return sig("ORDERBOOK_IMBALANCE","SHORT",min(10,abs(z)*20+2),"ask depth dominates")
    return sig("ORDERBOOK_IMBALANCE","NO_TRADE",0,"balanced book")

def momentum(s):
    x=features(s)
    if x["r5"]>.03 and x["d5"]>.05:return sig("MOMENTUM_CONTINUATION","LONG",min(10,abs(x["r5"])*1.5+abs(x["r30"])*.8+2),"price and flow aligned up")
    if x["r5"]<-.03 and x["d5"]<-.05:return sig("MOMENTUM_CONTINUATION","SHORT",min(10,abs(x["r5"])*1.5+abs(x["r30"])*.8+2),"price and flow aligned down")
    return sig("MOMENTUM_CONTINUATION","NO_TRADE",0,"no momentum alignment")

def mean_reversion(s):
    x=features(s)
    if x["r30"]<-.08 and x["d5"]>.08:return sig("MEAN_REVERSION","LONG",min(10,abs(x["r30"])*4+abs(x["d5"])*4),"down move with buying response")
    if x["r30"]>.08 and x["d5"]<-.08:return sig("MEAN_REVERSION","SHORT",min(10,abs(x["r30"])*4+abs(x["d5"])*4),"up move with selling response")
    return sig("MEAN_REVERSION","NO_TRADE",0,"no reversion")

def liquidity_sweep(s):
    x=features(s)
    if x["r5"]<-.06 and x["d5"]>.10 and x["imb5"]>0:return sig("LIQUIDITY_SWEEP","LONG",7,"selloff met by buying and bid support")
    if x["r5"]>.06 and x["d5"]<-.10 and x["imb5"]<0:return sig("LIQUIDITY_SWEEP","SHORT",7,"rally met by selling and ask support")
    return sig("LIQUIDITY_SWEEP","NO_TRADE",0,"no sweep confirmation")

def flow_follow(s):
    x=features(s)
    if x["d5"]>.15 and x["d30"]>.08 and x["imb5"]>-.05:return sig("FLOW_FOLLOW","LONG",min(10,x["d5"]*8+x["d30"]*5+3),"multi-window buying")
    if x["d5"]<-.15 and x["d30"]<-.08 and x["imb5"]<.05:return sig("FLOW_FOLLOW","SHORT",min(10,abs(x["d5"])*8+abs(x["d30"])*5+3),"multi-window selling")
    return sig("FLOW_FOLLOW","NO_TRADE",0,"flow not persistent")

def book_reversion(s):
    x=features(s)
    if x["imb5"]<-.25 and x["imb10"]>0:return sig("BOOK_REVERSION","LONG",6,"short book pressure conflicts with deeper book")
    if x["imb5"]>.25 and x["imb10"]<0:return sig("BOOK_REVERSION","SHORT",6,"short book pressure conflicts with deeper book")
    return sig("BOOK_REVERSION","NO_TRADE",0,"no book reversal")

def volatility_breakout(s):
    x=features(s)
    if abs(x["r5"])>.10 and x["r5"]*x["d5"]>0:return sig("VOLATILITY_BREAKOUT","LONG" if x["r5"]>0 else "SHORT",min(10,abs(x["r5"])*3+3),"large aligned short-term move")
    return sig("VOLATILITY_BREAKOUT","NO_TRADE",0,"no breakout")

def fisher_microstructure(s):
    x=features(s)
    if x["d5"]>.12 and x["imb5"]>.10 and x["r30"]>=0:return sig("FISHER_MICROSTRUCTURE_PROXY","LONG",7,"flow/book bullish confirmation")
    if x["d5"]<-.12 and x["imb5"]<-.10 and x["r30"]<=0:return sig("FISHER_MICROSTRUCTURE_PROXY","SHORT",7,"flow/book bearish confirmation")
    return sig("FISHER_MICROSTRUCTURE_PROXY","NO_TRADE",0,"no confirmation")

def pressure_exhaustion(s):
    x=features(s)
    if x["d5"]<-.20 and abs(x["r5"])<.03:return sig("PRESSURE_EXHAUSTION","LONG",7,"aggressive selling with price stalling")
    if x["d5"]>.20 and abs(x["r5"])<.03:return sig("PRESSURE_EXHAUSTION","SHORT",7,"aggressive buying with price stalling")
    return sig("PRESSURE_EXHAUSTION","NO_TRADE",0,"no exhaustion")

def trend_regime(s):
    x=features(s)
    if x["d60"]>.10 and x["d30"]>.08 and x["r60"]>0:return sig("TREND_REGIME","LONG",7,"60/30s bullish regime")
    if x["d60"]<-.10 and x["d30"]<-.08 and x["r60"]<0:return sig("TREND_REGIME","SHORT",7,"60/30s bearish regime")
    return sig("TREND_REGIME","NO_TRADE",0,"no trend regime")

STRATEGIES=(absorption,delta_divergence,orderbook_imbalance,momentum,mean_reversion,liquidity_sweep,flow_follow,book_reversion,volatility_breakout,fisher_microstructure,pressure_exhaustion,trend_regime)

def evaluate_all(state):return [fn(state) for fn in STRATEGIES]

def portfolio_pick(state):
    signals=[x for x in evaluate_all(state) if x.action!="NO_TRADE"]
    if not signals:return None,[]
    signals.sort(key=lambda x:x.score,reverse=True);return signals[0],signals
