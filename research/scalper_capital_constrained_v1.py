"""Capital-constrained portfolio simulation over shadow exits.
Research-only: no orders, no router changes, no live execution.
"""
from __future__ import annotations
import json, statistics
from collections import defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
J=ROOT/"data/processed/scalper_shadow_portfolio_v1.jsonl"
OUT=ROOT/"data/processed/scalper_capital_constrained_v1.json"

CAPITAL=1000.0
RISK_PER_TRADE=0.005
EPISODE_SEC=60
MAX_CONCURRENT=1


def load():
    out=[]
    if J.exists():
        for line in J.open():
            try:
                r=json.loads(line)
                if r.get("event")=="SHADOW_EXIT": out.append(r)
            except Exception: pass
    return sorted(out,key=lambda r:float(r["ts"]))


def simulate(rows, allowed):
    equity=CAPITAL; peak=equity; maxdd=0.0; trades=0; wins=0; pnl=[]
    episodes=defaultdict(list)
    for r in rows: episodes[int(float(r["ts"])//EPISODE_SEC)].append(r)
    for _,rs in sorted(episodes.items()):
        candidates=[r for r in rs if r["strategy"] in allowed]
        # One shared capital slot. Choose the best pre-known research score only
        # for analysis; this is not an executable selector and is not used live.
        if not candidates: continue
        r=max(candidates,key=lambda x:float(x.get("net_bps",0)))
        net=float(r.get("net_bps",0))
        risk=equity*RISK_PER_TRADE
        dollar=risk*(net/5.0)  # 5 bps stop-normalized unit risk
        equity+=dollar; pnl.append(dollar); trades+=1; wins+=net>0
        peak=max(peak,equity); maxdd=max(maxdd,(peak-equity)/peak)
    return {"trades":trades,"wins":wins,"win_rate":wins/trades if trades else 0,
            "ending_equity":equity,"return_pct":(equity/CAPITAL-1)*100,
            "max_drawdown_pct":maxdd*100,"avg_net_bps":statistics.mean([float(r.get("net_bps",0)) for r in rows if r["strategy"] in allowed]) if rows else 0,
            "pnl_usd":sum(pnl)}


def main():
    rows=load(); strategies=sorted({r["strategy"] for r in rows})
    corr=json.loads((ROOT/"data/processed/scalper_shadow_correlation_v1.json").read_text()) if (ROOT/"data/processed/scalper_shadow_correlation_v1.json").exists() else {}
    rank=[x["strategy"] for x in corr.get("strategies",[]) if x.get("episodes",0)>=2]
    top_sets={"TOP1":rank[:1],"TOP2":rank[:2],"TOP3":rank[:3],"TOP5":rank[:5],"ALL":strategies}
    results={k:simulate(rows,v) for k,v in top_sets.items()}
    result={"status":"RESEARCH_ONLY","capital_usd":CAPITAL,"risk_per_trade":RISK_PER_TRADE,
            "max_concurrent":MAX_CONCURRENT,"episode_seconds":EPISODE_SEC,
            "selection":"best observed exit within each episode; hindsight diagnostic only",
            "results":results,"live_orders":False}
    OUT.write_text(json.dumps(result,indent=2)); print(json.dumps(result,indent=2))

if __name__=="__main__": main()
