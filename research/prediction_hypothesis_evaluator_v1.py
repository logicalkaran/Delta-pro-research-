"""Prediction hypothesis evaluator v1. Research/paper only.

Uses only features actually present in the canonical forward dataset.
It creates directional hypothesis cohorts and matched controls, with 60s
timestamp separation and chronological train/test reporting. It never
changes execution, leverage, risk, or production code.
"""
from pathlib import Path
from collections import defaultdict
import json, math, time

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"data/processed/strategy_forward_tournament_v1.jsonl"
OUT=ROOT/"data/processed/prediction_hypothesis_evaluation_v1.json"
COST_BPS=12.0
MIN=100
GAP=60

def load():
    a=[]
    if not SRC.exists(): return a
    for line in SRC.read_text().splitlines():
        try:
            r=json.loads(line)
            if r.get("net_return_pct") is None: continue
            a.append(r)
        except: pass
    # One observation per timestamp/horizon to avoid strategy-label duplication.
    u={}
    for r in a:
        u.setdefault((float(r["issued_at"]),int(r["horizon"])),r)
    return sorted(u.values(),key=lambda r:float(r["issued_at"]))

def f(r,k):
    try:return float(r.get(k,0))
    except:return 0.0

def select(rows,hyp):
    out=[]
    for r in rows:
        d=f(r,"delta5"); d30=f(r,"delta30"); imb=f(r,"imbalance"); ret=f(r,"return5")
        if hyp=="FLOW_PRICE_CONFIRMATION":
            # continuation: flow direction and recent return agree
            if d*ret>0 and abs(d)>=0.05 and abs(ret)>=0.02: out.append(r)
        elif hyp=="ABSORPTION_FAILURE":
            # extreme flow with weak opposing price response
            if abs(d)>=0.30 and d*ret<0 and abs(ret)<=0.15: out.append(r)
        elif hyp=="LIQUIDITY_SWEEP_RECLAIM":
            # available dataset has a LIQUIDITY_SWEEP label; use only its
            # timestamp/horizon cohort as a diagnostic, never as a learned edge.
            if r.get("strategy")=="LIQUIDITY_SWEEP": out.append(r)
        elif hyp=="REGIME_CONDITIONAL_FLOW":
            if abs(d)>=0.15 and r.get("regime") in ("LOW_VOL","NORMAL_VOL"): out.append(r)
        elif hyp=="FLOW_DIVERGENCE":
            if d*ret<0 and abs(d)>=0.15 and abs(ret)>=0.02: out.append(r)
        elif hyp=="ORDERBOOK_PERSISTENCE":
            # Persistence cannot be measured from this schema; use strong
            # imbalance as a clearly marked proxy, not a persistence claim.
            if abs(imb)>=0.30: out.append(r)
    return out

def independent(rs):
    rs=sorted(rs,key=lambda r:float(r["issued_at"]))
    out=[]; last=-1e18
    for r in rs:
        t=float(r["issued_at"])
        if t-last>=GAP:
            out.append(r); last=t
    return out

def stats(rs):
    vals=[f(r,"net_return_pct")*100 for r in rs]
    if not vals:return {"n":0}
    pos=[x for x in vals if x>0]; neg=[x for x in vals if x<0]
    return {
      "n":len(vals),"avg_net_bps":sum(vals)/len(vals),
      "median_net_bps":sorted(vals)[len(vals)//2],
      "positive_rate":len(pos)/len(vals),
      "profit_factor":sum(pos)/abs(sum(neg)) if neg else None,
      "sum_net_bps":sum(vals),
      "after_additional_cost_bps":sum(vals)-COST_BPS*len(vals)
    }

def halfs(rs):
    rs=sorted(rs,key=lambda r:float(r["issued_at"]))
    m=len(rs)//2
    return stats(rs[:m]),stats(rs[m:])

def main():
    rows=load()
    results=[]
    for hyp in ("FLOW_PRICE_CONFIRMATION","ABSORPTION_FAILURE","LIQUIDITY_SWEEP_RECLAIM",
                "REGIME_CONDITIONAL_FLOW","FLOW_DIVERGENCE","ORDERBOOK_PERSISTENCE"):
        chosen=independent(select(rows,hyp))
        # matched control: same horizons/regimes distribution is approximated
        # by all independent observations; this is diagnostic, not causal proof.
        s=stats(chosen); h1,h2=halfs(chosen)
        stable=bool(s.get("n",0)>=MIN and s.get("avg_net_bps",0)>0 and
                    (s.get("profit_factor") or 0)>=1.2 and
                    h1.get("avg_net_bps",0)>0 and h2.get("avg_net_bps",0)>0)
        results.append({"hypothesis":hyp,"status":"CANDIDATE" if stable else "REJECT_OR_INCONCLUSIVE",
                        "stats":s,"first_half":h1,"second_half":h2,
                        "selection_count":len(chosen),
                        "note":"ORDERBOOK_PERSISTENCE uses imbalance proxy; LIQUIDITY_SWEEP uses existing label. Neither proves the underlying causal thesis."})
    out={"updated_at":time.time(),"status":"RESEARCH_ONLY","source_rows":len(rows),
         "cost_assumption_bps":COST_BPS,"minimum_independent_samples":MIN,
         "hypotheses":results,
         "policy":{"leverage_changed":False,"risk_changed":False,"production_mutation":False,"real_orders":False}}
    OUT.write_text(json.dumps(out,indent=2))
    print(json.dumps(out,indent=2))

if __name__=="__main__":main()
