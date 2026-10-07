"""Correlation-aware analysis for standalone 12-strategy shadow results.
Research-only; never enables live execution.
"""
from __future__ import annotations
import json, math, statistics
from collections import defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
JOURNAL=ROOT/"data/processed/scalper_shadow_portfolio_v1.jsonl"
OUT=ROOT/"data/processed/scalper_shadow_correlation_v1.json"


def main():
    exits=[]
    if JOURNAL.exists():
        for line in JOURNAL.open():
            try:
                r=json.loads(line)
                if r.get("event")=="SHADOW_EXIT": exits.append(r)
            except Exception: pass
    episodes=defaultdict(list)
    for r in exits: episodes[int(float(r["ts"])//60)].append(r)
    strategies=sorted({r["strategy"] for r in exits})
    ep_values=defaultdict(dict)
    for eid,rs in episodes.items():
        for r in rs: ep_values[eid][r["strategy"]]=float(r["net_bps"])
    rows=[]
    for s in strategies:
        vals=[v[s] for v in ep_values.values() if s in v]
        positive=sum(v>0 for v in vals)
        raw_avg=statistics.mean(vals) if vals else 0.0
        # Episode-normalized contribution: each episode has equal weight.
        rows.append({"strategy":s,"episodes":len(vals),"positive_episodes":positive,
                     "episode_win_rate":positive/len(vals) if vals else 0.0,
                     "episode_avg_net_bps":raw_avg,
                     "raw_sum_net_bps":sum(vals)})
    # Pairwise directional agreement.  This is a descriptive correlation proxy
    # that remains usable with sparse, uneven episode coverage.
    pair={}
    for i,a in enumerate(strategies):
        for b in strategies[i+1:]:
            common=[(v[a],v[b]) for v in ep_values.values() if a in v and b in v]
            if len(common)<2: continue
            same=sum((x>0)==(y>0) for x,y in common)/len(common)
            pair[f"{a}|{b}"]={"common_episodes":len(common),"directional_agreement":same}
    # Independence-adjusted score: average episode edge divided by exposure
    # to other strategies' same-direction outcomes.
    for row in rows:
        s=row["strategy"]
        agreements=[]
        for key,p in pair.items():
            if s in key and p["common_episodes"]>=2: agreements.append(p["directional_agreement"])
        redundancy=statistics.mean(agreements) if agreements else 0.0
        row["mean_directional_redundancy"]=redundancy
        row["independence_adjusted_score"]=row["episode_avg_net_bps"]*(1.0-0.5*redundancy)
    rows.sort(key=lambda x:x["independence_adjusted_score"],reverse=True)
    result={"status":"RESEARCH_ONLY","exits":len(exits),"episodes":len(episodes),
            "strategies":rows,"pairwise":pair,"live_orders":False}
    OUT.write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))

if __name__=="__main__": main()
