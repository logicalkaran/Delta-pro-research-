"""Read-only intraday setup detector for dashboard visualization."""
from __future__ import annotations
import json, os, time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
OUT=ROOT/"data/live_signal_state.json"

def compute(candles, live, fisher):
    if len(candles)<5 or not live: return {"decision":"WAIT","confidence":0,"reason_codes":["INSUFFICIENT_INTRADAY_DATA"]}
    recent=candles[-5:]; last=recent[-1]; closes=[float(x["close"]) for x in recent]
    up=all(closes[i]>=closes[i-1] for i in range(1,len(closes)))
    down=all(closes[i]<=closes[i-1] for i in range(1,len(closes)))
    bid=float(live.get("bid_size",0)); ask=float(live.get("ask_size",0)); flow=bid/(ask or 1)
    f=float((fisher or {}).get("fisher",0)); cross=bool((fisher or {}).get("bullish_cross",False))
    decision="WAIT"; reasons=[]
    if up and flow>=1.25 and f>0: decision="LONG"; reasons=["INTRADAY_UPTREND","BID_PRESSURE","FISHER_BULLISH"]
    elif down and flow<=0.8 and f<0: decision="SHORT"; reasons=["INTRADAY_DOWNTREND","ASK_PRESSURE","FISHER_BEARISH"]
    else: reasons=["SETUP_NOT_CONFIRMED"]
    confidence=min(0.95,0.45+0.1*len(reasons)) if decision!="WAIT" else 0.0
    entry=float(live.get("mid_price") or last["close"])
    rng=max(float(last["high"])-float(last["low"]),entry*0.001)
    sl=entry-rng*1.5 if decision=="LONG" else entry+rng*1.5 if decision=="SHORT" else None
    tp=entry+rng*3 if decision=="LONG" else entry-rng*3 if decision=="SHORT" else None
    return {"timestamp":int(time.time()),"decision":decision,"confidence":round(confidence,3),"entry":entry,"stop_loss":sl,"take_profit":tp,"reason_codes":reasons,"fisher_cross":cross}

def update():
    def read(name,default):
        p=ROOT/"data"/name
        try:return json.loads(p.read_text())
        except Exception:return default
    candles=read("live_candles.json",[]); live=read("live_market_state.json",{}); f=read("live_fisher_state.json",{})
    result=compute(candles,live,f); OUT.write_text(json.dumps(result,indent=2),encoding="utf-8"); return result
