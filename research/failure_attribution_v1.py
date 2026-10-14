"""Deterministic failure attribution for BTC paper execution V3.

Research-only. Reads closed paper trades and identifies statistically meaningful
loss cohorts plus structural target/stop geometry problems. Never changes live
execution settings and never submits orders.
"""
from __future__ import annotations
import json, math, statistics
from collections import defaultdict, Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRADES = ROOT / "data/processed/live_execution_paper_v3.jsonl"
OUT = ROOT / "data/processed/failure_attribution_v1.json"

def stat(rows):
    vals=[float(r["net_bps"]) for r in rows]
    wins=[v for v in vals if v>0]
    losses=[-v for v in vals if v<0]
    return {
        "n": len(vals),
        "win_rate": round(len(wins)/len(vals),4) if vals else 0.0,
        "avg_net_bps": round(statistics.mean(vals),4) if vals else 0.0,
        "sum_net_bps": round(sum(vals),4),
        "profit_factor": round(sum(wins)/sum(losses),4) if losses else None,
    }

def load_pairs():
    entries=[]; exits=[]
    for line in TRADES.read_text(encoding="utf-8").splitlines():
        if not line.strip(): continue
        d=json.loads(line)
        if d.get("event")=="PAPER_ENTRY":
            entries.append(d["position"])
        elif d.get("event")=="PAPER_EXIT":
            exits.append(d)
    rows=[]
    for pos, ex in zip(entries, exits):
        entry=float(pos["entry"])
        stop=float(pos["stop"])
        target=float(pos["target"])
        nearest=(pos.get("resistance") if pos["side"]=="LONG" else pos.get("support"))
        stop_bps=abs(entry-stop)/entry*10000
        target_bps=abs(target-entry)/entry*10000
        nearest_bps=abs(float(nearest)-entry)/entry*10000 if nearest else None
        rows.append({
            "side":pos.get("side"),
            "signal_reason":pos.get("signal_reason"),
            "regime":pos.get("regime"),
            "exit_reason":ex.get("exit_reason"),
            "net_bps":float(ex.get("net_bps",0)),
            "hold_s":float(ex.get("hold_s",0)),
            "rr":target_bps/stop_bps if stop_bps else 0.0,
            "stop_bps":stop_bps,
            "target_bps":target_bps,
            "nearest_target_bps":nearest_bps,
            "target_jump": nearest_bps is not None and nearest_bps < 1.5*stop_bps,
            "remote_target": target_bps > 4.0*(float(pos.get("atr") or entry*0.0008))/entry*10000,
        })
    return rows

def main():
    rows=load_pairs()
    cohorts={}
    for key in ("side","signal_reason","regime","exit_reason"):
        g=defaultdict(list)
        for r in rows: g[r.get(key)].append(r)
        cohorts[key]={str(k):stat(v) for k,v in sorted(g.items(), key=lambda x:len(x[1]), reverse=True)}
    target_jump=[r for r in rows if r["target_jump"]]
    clean=[r for r in rows if not r["target_jump"]]
    hold_buckets={}
    for lo,hi in ((0,10),(10,30),(30,120),(120,300),(300,901)):
        hold_buckets[f"{lo}-{hi}s"]=stat([r for r in rows if lo<=r["hold_s"]<hi])
    result={
        "status":"RESEARCH_ONLY",
        "trades":len(rows),
        "overall":stat(rows),
        "cohorts":cohorts,
        "hold_buckets":hold_buckets,
        "geometry": {
            "near_target_below_1_5R_count":len(target_jump),
            "near_target_below_1_5R_share":round(len(target_jump)/len(rows),4) if rows else 0.0,
            "all_avg_net_bps":stat(rows)["avg_net_bps"],
            "clean_avg_net_bps":stat(clean)["avg_net_bps"],
            "clean":stat(clean),
            "target_jump":stat(target_jump),
        },
        "conclusion":[
            "The historical V3 sample is not production profitable.",
            "The target selector previously skipped nearby opposing levels when they failed the RR floor, manufacturing remote targets.",
            "The sample is entirely LOW_VOLATILITY, so low-volatility performance is the only observed regime and is currently blocked by default.",
            "These findings justify paper/shadow gating changes but do not establish profitability in a new regime."
        ],
        "real_orders":False,
    }
    OUT.write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps(result,indent=2))

if __name__=="__main__":
    main()
