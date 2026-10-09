"""Prospective walk-forward selector over shadow exits.
Uses only completed episodes strictly before each test episode.
Research-only; never modifies execution or enables live trading.
"""
from __future__ import annotations
import json, statistics
from collections import defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
J=ROOT/"data/processed/scalper_shadow_portfolio_v1.jsonl"
OUT=ROOT/"data/processed/scalper_walkforward_selector_v1.json"
EP_SEC=60
MIN_HISTORY=2


def load():
    rows=[]
    if J.exists():
        for line in J.open():
            try:
                r=json.loads(line)
                if r.get("event")=="SHADOW_EXIT": rows.append(r)
            except Exception: pass
    return sorted(rows,key=lambda r:float(r["ts"]))


def main():
    rows=load(); episodes=defaultdict(list)
    for r in rows: episodes[int(float(r["ts"])//EP_SEC)].append(r)
    history=defaultdict(list); chosen=[]; equity=1000.0
    for eid,rs in sorted(episodes.items()):
        eligible={s:vals for s,vals in history.items() if len(vals)>=MIN_HISTORY}
        if not eligible:
            for r in rs: history[r["strategy"]].append(float(r["net_bps"]))
            continue
        def score(item):
            s,vals=item
            # Prior-only score: mean net bps with a small sample penalty.
            mean=statistics.mean(vals); penalty=2.0/(len(vals)**0.5)
            return mean-penalty
        strategy=max(eligible.items(),key=score)[0]
        candidates=[r for r in rs if r["strategy"]==strategy]
        if candidates:
            r=candidates[0]; net=float(r["net_bps"]); chosen.append({"episode":eid,"strategy":strategy,"net_bps":net,"history_n":len(eligible[strategy])})
            equity*=1.0+0.005*(net/5.0)
        for r in rs: history[r["strategy"]].append(float(r["net_bps"]))
    vals=[x["net_bps"] for x in chosen]
    wins=sum(v>0 for v in vals)
    result={"status":"RESEARCH_ONLY","episodes":len(episodes),"selected_trades":len(vals),
            "win_rate":wins/len(vals) if vals else 0,"avg_net_bps":statistics.mean(vals) if vals else 0,
            "sum_net_bps":sum(vals),"ending_equity":equity,"return_pct":(equity/1000-1)*100,
            "selections":chosen,"rule":"prior-history mean minus sqrt-sample penalty","live_orders":False}
    OUT.write_text(json.dumps(result,indent=2)); print(json.dumps(result,indent=2))

if __name__=="__main__": main()
