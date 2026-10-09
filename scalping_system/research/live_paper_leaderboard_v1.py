"""Live paper leaderboard for the professional scalper portfolio.

Reads completed paper exits and produces strategy/route rankings. It never
places orders and never changes strategy parameters.
"""
from __future__ import annotations
import json,math,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
JOURNAL=ROOT/"data/processed/scalper_portfolio_paper_v1.jsonl"
OUT=ROOT/"data/processed/scalper_portfolio_leaderboard_v1.json"

def load():
    rows=[]
    if not JOURNAL.exists(): return rows
    for line in JOURNAL.read_text().splitlines():
        try: rows.append(json.loads(line))
        except Exception: pass
    return rows

def group(rows,key):
    out={}
    for r in rows:
        if r.get("event")!="PAPER_EXIT": continue
        k=r.get(key,"UNKNOWN");d=out.setdefault(k,{"trades":0,"wins":0,"losses":0,"net_bps":0.0,"gross_wins":0.0,"gross_losses":0.0})
        n=float(r.get("net_bps",0));d["trades"]+=1;d["wins"]+=n>0;d["losses"]+=n<=0;d["net_bps"]+=n
        if n>0:d["gross_wins"]+=n
        else:d["gross_losses"]-=n
    for d in out.values():
        d["win_rate"]=d["wins"]/d["trades"] if d["trades"] else 0
        d["avg_net_bps"]=d["net_bps"]/d["trades"] if d["trades"] else 0
        d["profit_factor"]=d["gross_wins"]/d["gross_losses"] if d["gross_losses"] else None
        # Confidence grows slowly; a 1-trade winner must not outrank mature evidence.
        d["evidence_score"]=min(1.0,d["trades"]/100)*max(0.0,min(1.0,(d["avg_net_bps"]+1)/3))
        d["eligible_for_promotion"]=d["trades"]>=100 and d["win_rate"]>=.52 and (d["profit_factor"] or 0)>=1.20 and d["avg_net_bps"]>=.50
    return out

def main():
    rows=load();strategies=group(rows,"strategy");routes=group(rows,"route")
    ranking=sorted(strategies.items(),key=lambda kv:(kv[1]["eligible_for_promotion"],kv[1]["evidence_score"],kv[1]["avg_net_bps"]),reverse=True)
    result={"generated_at":time.time(),"status":"PAPER_ANALYSIS_ONLY","real_orders":False,
            "completed_trades":sum(x.get("trades",0) for x in strategies.values()),
            "strategy_ranking":[{"strategy":k,**v} for k,v in ranking],
            "route_ranking":[{"route":k,**v} for k,v in sorted(routes.items(),key=lambda kv:kv[1]["avg_net_bps"],reverse=True)],
            "promotion":"BLOCKED_UNTIL_GLOBAL_GATE"}
    OUT.write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
if __name__=="__main__":main()
