"""Multi-timeframe research context builder. Research/paper only.

5m/15m/1h are contextual layers for scalping and swing research.
They do not alter leverage, risk, execution, or production strategy.
"""
from pathlib import Path
import json,time,statistics
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"data/live_candles.json"
OUT=ROOT/"data/processed/multi_timeframe_context_v1.json"
H={"5m":5,"15m":15,"1h":60}

def f(x,d=0):
    try:return float(x)
    except:return d

def ema(a,n):
    if not a:return 0
    x=a[0]; k=2/(n+1)
    for v in a[1:]: x=k*v+(1-k)*x
    return x

def atr(c,n=14):
    if len(c)<2:return 0
    tr=[]
    for i in range(1,len(c)):
        h,l,pc=f(c[i]["high"]),f(c[i]["low"]),f(c[i-1]["close"])
        tr.append(max(h-l,abs(h-pc),abs(l-pc)))
    return statistics.mean(tr[-n:]) if tr else 0

def resample(c,minutes):
    step=minutes*60; buckets={}
    for x in c:
        t=int(f(x.get("timestamp")))
        b=t-(t%step)
        z=buckets.setdefault(b,{"timestamp":b,"open":None,"high":-1e99,"low":1e99,"close":None,"volume":0,"trades":0})
        o,h,l,cl=f(x.get("open")),f(x.get("high")),f(x.get("low")),f(x.get("close"))
        if z["open"] is None:z["open"]=o
        z["high"]=max(z["high"],h); z["low"]=min(z["low"],l); z["close"]=cl
        z["volume"]+=f(x.get("volume")); z["trades"]+=int(f(x.get("trades")))
    return [buckets[k] for k in sorted(buckets)]

def context(c):
    closes=[f(x["close"]) for x in c]
    if len(closes)<30:return {"samples":len(c),"ready":False}
    px=closes[-1]; e9=ema(closes[-30:],9); e21=ema(closes[-30:],21); a=atr(c)
    r1=px/closes[-2]-1; r3=px/closes[-4]-1; r10=px/closes[-11]-1
    trend="UP" if e9>e21 and r3>0 else ("DOWN" if e9<e21 and r3<0 else "MIXED")
    vol=a/px if px else 0
    regime="HIGH_VOL" if vol>.002 else ("LOW_VOL" if vol<.0007 else "NORMAL_VOL")
    return {"samples":len(c),"ready":True,"price":px,"ema9":e9,"ema21":e21,
            "return1":r1,"return3":r3,"return10":r10,"atr":a,"atr_pct":vol*100,
            "trend":trend,"regime":regime}

def main():
    raw=json.loads(SRC.read_text()) if SRC.exists() else []
    out={"updated_at":time.time(),"status":"RESEARCH_ONLY","timeframes":{},"policy":{
        "leverage_changed":False,"risk_changed":False,"production_mutation":False,"real_orders":False}}
    for name,m in H.items():
        c=resample(raw,m); out["timeframes"][name]=context(c)
    # Cross-timeframe alignment is deliberately descriptive, not a trade signal.
    cs=out["timeframes"]
    trends=[cs[x].get("trend") for x in ("5m","15m","1h") if cs[x].get("ready")]
    out["alignment"]="ALIGNED_UP" if trends and all(x=="UP" for x in trends) else ("ALIGNED_DOWN" if trends and all(x=="DOWN" for x in trends) else "MIXED")
    OUT.write_text(json.dumps(out,indent=2))
    print(json.dumps(out,indent=2))

if __name__=="__main__":main()
