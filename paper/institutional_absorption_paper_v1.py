"""Live-data shadow/paper runner for the institutional absorption strategy.

No credentials and no order submission. It reads the existing Delta microstructure
state, public Binance/Bybit OI snapshots, and Delta 1m/5m candles.
"""
from __future__ import annotations
import json, os, time, urllib.parse, urllib.request
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from strategy.institutional_absorption_v1 import evaluate, AbsorptionConfig

OUT=ROOT/"data/processed/institutional_absorption_paper_v1.jsonl"
SUMMARY=ROOT/"data/processed/institutional_absorption_paper_v1_summary.json"

def get(url, timeout=4):
    req=urllib.request.Request(url,headers={"User-Agent":"btc-institutional-absorption-v1/1.0","Accept":"application/json"})
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return json.loads(r.read().decode())

def candles(res):
    now=int(time.time()); start=now-(240*60 if res=="1m" else 120*300)
    q=urllib.parse.urlencode({"resolution":res,"symbol":"BTCUSD","start":start,"end":now})
    d=get("https://api.india.delta.exchange/v2/history/candles?"+q)
    if not d.get("success",True): raise RuntimeError("Delta candle API unsuccessful")
    rows=d.get("result",[])
    return sorted(rows,key=lambda x:x.get("time",0))

def cross_venue():
    path=ROOT/"data/processed/cross_venue_btc_v43.jsonl"
    if not path.exists(): return {}, 0.0
    rows=[]
    with path.open() as f:
        for line in f.readlines()[-20:]:
            try: rows.append(json.loads(line))
            except json.JSONDecodeError: pass
    oi=[]
    for row in rows:
        ts=row.get("epoch_ms",0)
        for v in row.get("comparison",{}).get("venues",[]):
            if v.get("venue") in ("binance","bybit") and float(v.get("open_interest") or 0)>0:
                oi.append((ts,v["venue"],float(v["open_interest"])))
    if len(oi)<2: return (rows[-1] if rows else {}), 0.0
    by={}
    for ts,venue,val in oi: by.setdefault(venue,[]).append((ts,val))
    changes=[]
    for vals in by.values():
        vals=sorted(vals)
        latest=vals[-1][1]
        older=next((v for t,v in reversed(vals[:-1]) if vals[-1][0]-t>=15000), vals[0][1])
        if older>0: changes.append((latest/older-1)*100)
    return (rows[-1] if rows else {}), (sum(changes)/len(changes) if changes else 0.0)

def run_once():
    micro=json.loads((ROOT/"data/live_microstructure_state.json").read_text())
    cross, oi_change=cross_venue()
    c1=candles("1m"); c5=candles("5m")
    # Reuse the existing predictive-level POC if available; otherwise the strategy computes a local POC.
    poc=None
    p=ROOT/"data/processed/predictive_levels_live.json"
    if p.exists():
        try: poc=float(json.loads(p.read_text()).get("poc") or 0) or None
        except Exception: poc=None
    sig=evaluate(micro,c1,c5,oi_change_pct=oi_change,poc=poc,cfg=AbsorptionConfig())
    row={"ts":int(time.time()),"signal":sig.__dict__,"oi_change_pct":oi_change,
         "micro_timestamp":micro.get("timestamp"),"candle_1m":len(c1),"candle_5m":len(c5),
         "paper_only":True,"real_orders":False}
    OUT.parent.mkdir(parents=True,exist_ok=True)
    with OUT.open("a") as f:f.write(json.dumps(row,separators=(",",":"))+"\n")
    return row

def summarize():
    if not OUT.exists(): return {}
    rows=[]
    with OUT.open() as f:
        for line in f:
            try: rows.append(json.loads(line))
            except: pass
    signals=[r["signal"] for r in rows if r.get("signal",{}).get("valid")]
    data={"updated_at":int(time.time()),"evaluations":len(rows),"valid_signals":len(signals),
          "long_signals":sum(s["action"]=="LONG" for s in signals),
          "short_signals":sum(s["action"]=="SHORT" for s in signals),
          "paper_only":True,"real_orders":False,
          "latest":rows[-1] if rows else None}
    SUMMARY.write_text(json.dumps(data,indent=2))
    return data

if __name__=="__main__":
    row=run_once()
    print(json.dumps({"action":row["signal"]["action"],"confidence":row["signal"]["confidence"],
                      "rr":row["signal"]["rr"],"reason":row["signal"]["reason"],
                      "oi_change_pct":row["oi_change_pct"]},separators=(",",":")))
    print(json.dumps(summarize(),separators=(",",":")))
