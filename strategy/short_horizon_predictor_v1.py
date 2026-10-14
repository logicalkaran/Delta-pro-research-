"""Robust 1-5 minute BTC movement and S/R predictor. Research/paper only."""
from dataclasses import dataclass,asdict
from statistics import mean,median
from math import sqrt,exp
@dataclass(frozen=True)
class HorizonForecast:
    minutes:int; direction:str; probability_up:float; expected_return_pct:float; range_pct:float; confidence:float
@dataclass(frozen=True)
class ShortHorizonPrediction:
    price:float; forecasts:tuple; support:tuple; resistance:tuple; regime:str; execution_bias:str; confidence:float; data_quality:float
    def to_dict(self): return asdict(self)
def f(x,d=0.0):
    try:return float(x)
    except:return d
def rows(candles):
    out=[]
    for c in candles:
        o,h,l,cl,v=(f(c.get(k)) for k in ("open","high","low","close","volume"))
        if min(h,l,cl)<=0 or h<l: continue
        out.append((o,h,l,cl,max(v,0),f(c.get("timestamp"))))
    return out
def atr(rs,n=14):
    if len(rs)<2:return 0
    tr=[]
    for i in range(1,len(rs)):
        _,h,l,cl,_,_=rs[i]; pc=rs[i-1][3]
        tr.append(max(h-l,abs(h-pc),abs(l-pc)))
    return mean(tr[-n:]) if tr else 0
def ret(rs,n):
    return rs[-1][3]/rs[-1-n][3]-1 if len(rs)>n else 0
def ema(vals,n):
    if not vals:return 0
    a=2/(n+1); x=vals[0]
    for v in vals[1:]: x=a*v+(1-a)*x
    return x
def predict(candles,levels=None,state=None):
    rs=rows(candles)[-240:]
    state=state or {}
    px=rs[-1][3] if rs else f(state.get("order_book",{}).get("mid_price"))
    if not rs or px<=0:return ShortHorizonPrediction(px,(),(),(),"UNKNOWN","NEUTRAL",0,0)
    a=atr(rs); closes=[x[3] for x in rs]; vols=[x[4] for x in rs]
    r1,r3,r5=ret(rs,1),ret(rs,3),ret(rs,5)
    fast=ema(closes[-30:],8); slow=ema(closes[-60:],21); trend=(fast/slow-1) if slow else 0
    vol_ratio=vols[-1]/(median(vols[-30:]) or 1)
    ob=state.get("order_book",{}); imb=f(ob.get("imbalance_5"))
    d5=f(state.get("windows",{}).get("5",{}).get("delta_pct")); d30=f(state.get("windows",{}).get("30",{}).get("delta_pct"))
    fresh=f(state.get("quality",{}).get("fresh_seconds"),999)
    quality=1.0 if fresh<=1 else max(.25,1-fresh/10)
    if len(rs)<60: quality*=max(.25,len(rs)/60)
    if vol_ratio>2.5: quality*=.90
    regime="HIGH_VOLATILITY" if a/px>.0018 else ("LOW_VOLATILITY" if a/px<.0007 else "NORMAL")
    momentum=.30*(r1/.0008)+.25*(r3/.0015)+.20*(r5/.0025)+.25*(trend/.0015)
    flow=.45*(d5/.25)+.30*(d30/.40)+.25*(imb/.15)
    raw=max(-2.5,min(2.5,momentum+flow))
    p_up=1/(1+exp(-raw))
    forecasts=[]
    for m in range(1,6):
        decay=1/(1+0.30*(m-1))
        # Horizon uncertainty grows with time; do not claim identical confidence at every horizon.
        horizon_edge=(p_up-.5)*decay
        er=horizon_edge*2*(a/px)*sqrt(m)
        band=(a/px)*sqrt(m)*(1.10+0.08*m)
        conf=min(.90,max(.05,0.50+abs(horizon_edge)*.80))*quality
        direction="UP" if horizon_edge>.06 else ("DOWN" if horizon_edge<-.06 else "NEUTRAL")
        forecasts.append(HorizonForecast(m,direction,round(.5+horizon_edge,4),round(er*100,4),round(band*100,4),round(conf,4)))
    sup=[]; res=[]
    if levels:
        sup=[x.price for x in getattr(levels,"support",())[:4]]
        res=[x.price for x in getattr(levels,"resistance",())[:4]]
    if not sup:sup=[px-a,px-2*a]
    if not res:res=[px+a,px+2*a]
    p5=forecasts[4].probability_up
    bias="LONG" if p5>=.60 else ("SHORT" if p5<=.40 else "WAIT")
    return ShortHorizonPrediction(round(px,2),tuple(forecasts),tuple(round(x,2) for x in sup),tuple(round(x,2) for x in res),regime,bias,round(min(x.confidence for x in forecasts),4),round(quality,4))
