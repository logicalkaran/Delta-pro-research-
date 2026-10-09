"""Adaptive event engine v1.
Research-only. No leverage/risk/execution authority.
Learns event thresholds from past data and scores current events by
chronological, cost-adjusted evidence. Never uses future labels for selection.
"""
from __future__ import annotations
import json, math, statistics, time
from pathlib import Path
from collections import defaultdict
ROOT=Path(__file__).resolve().parents[1]
LAB=ROOT/"data/processed/live_microstructure_labeled_v1.jsonl"
OUT=ROOT/"data/processed/adaptive_event_engine_v1.json"
COST=10.76
HORIZONS=(60,120,180,300)

FEATURES=("imb5","imb10","delta5","delta30","delta60","ret5","ret30","ret60","cvd_slope30","spread_bps")

def num(x):
    try:
        x=float(x)
        return x if math.isfinite(x) else None
    except Exception: return None

def load():
    rows=[]
    if LAB.exists():
        for line in LAB.read_text().splitlines():
            try:
                r=json.loads(line)
                if isinstance(r,dict) and isinstance(r.get("labels"),dict):
                    rows.append(r)
            except Exception: pass
    return sorted(rows,key=lambda r:float(r.get("ts",0)))

def quantile(vals,p):
    vals=sorted(v for v in vals if v is not None)
    if not vals: return None
    i=(len(vals)-1)*p; lo=int(i); hi=min(lo+1,len(vals)-1); a=i-lo
    return vals[lo]*(1-a)+vals[hi]*a

def build_thresholds(train):
    t={}
    for k in FEATURES:
        vals=[num(r.get(k)) for r in train]
        vals=[v for v in vals if v is not None]
        t[k]=(quantile(vals,.2),quantile(vals,.8))
    return t

def event_vector(r,t):
    vals={k:num(r.get(k)) for k in FEATURES}
    if any(vals[k] is None for k in ("imb5","delta5","delta30","ret5","ret30")):
        return {}
    il,ih=t["imb5"]; d5l,d5h=t["delta5"]; d30l,d30h=t["delta30"]; r5l,r5h=t["ret5"]; r30l,r30h=t["ret30"]
    return {
      "sweep_reclaim_long": r5l is not None and vals["ret5"]<=r5l and vals["ret30"]>=0 and vals["imb5"]>=ih,
      "sweep_reclaim_short": r5h is not None and vals["ret5"]>=r5h and vals["ret30"]<=0 and vals["imb5"]<=il,
      "flow_confirm_long": vals["delta30"]>=d30h and vals["ret30"]>=r30h and vals["imb5"]>=ih,
      "flow_confirm_short": vals["delta30"]<=d30l and vals["ret30"]<=r30l and vals["imb5"]<=il,
      "absorption_long": vals["delta30"]>=d30h and abs(vals["ret30"])<=max(abs(r30l),abs(r30h))*.35,
      "absorption_short": vals["delta30"]<=d30l and abs(vals["ret30"])<=max(abs(r30l),abs(r30h))*.35,
      "imbalance_reversal_long": vals["imb5"]>=ih and vals["delta5"]>=d5h and vals["ret5"]>=0,
      "imbalance_reversal_short": vals["imb5"]<=il and vals["delta5"]<=d5l and vals["ret5"]<=0,
    }

def score(train,test):
    t=build_thresholds(train)
    # Calibrate each event independently using only train labels.
    stats=defaultdict(list)
    for r in train:
        ev=event_vector(r,t)
        for name,hit in ev.items():
            if not hit: continue
            side=1 if name.endswith("long") else -1
            for h in HORIZONS:
                lab=r.get("labels",{}).get(str(h),{})
                y=num(lab.get("move_bps")) if isinstance(lab,dict) else None
                if y is not None: stats[(name,h)].append(side*y)
    calibration={}
    for key,ys in stats.items():
        if len(ys)>=20:
            calibration[key]={
              "n":len(ys),"mean_bps":statistics.fmean(ys),
              "median_bps":statistics.median(ys),
              "positive_rate":sum(y>0 for y in ys)/len(ys),
              "std_bps":statistics.pstdev(ys) if len(ys)>1 else 0
            }
    # Evaluate chronological holdout.
    results=[]
    for r in test:
        ev=event_vector(r,t)
        for name,hit in ev.items():
            if not hit: continue
            side=1 if name.endswith("long") else -1
            for h in HORIZONS:
                c=calibration.get((name,h))
                lab=r.get("labels",{}).get(str(h),{})
                y=num(lab.get("move_bps")) if isinstance(lab,dict) else None
                if c is None or y is None: continue
                results.append({"event":name,"horizon_s":h,"predicted_gross_bps":c["mean_bps"],
                    "actual_bps":side*y,"net_actual_bps":side*y-COST})
    return t,calibration,results

def main():
    rows=load()
    if len(rows)<300:
        out={"status":"INSUFFICIENT_DATA","rows":len(rows),"research_only":True,"real_orders":False}
    else:
        cut=int(len(rows)*.65)
        t,c,res=score(rows[:cut],rows[cut:])
        grouped=defaultdict(list)
        for x in res: grouped[(x["event"],x["horizon_s"])].append(x["net_actual_bps"])
        cohorts=[]
        for (event,h),ys in grouped.items():
            if len(ys)<20: continue
            mid=len(ys)//2
            cohorts.append({"event":event,"horizon_s":h,"n":len(ys),
              "avg_net_bps":statistics.fmean(ys),
              "first_half_net_bps":statistics.fmean(ys[:mid]),
              "second_half_net_bps":statistics.fmean(ys[mid:]),
              "positive_rate":sum(y>0 for y in ys)/len(ys),
              "stable_positive":statistics.fmean(ys)>0 and statistics.fmean(ys[:mid])>0 and statistics.fmean(ys[mid:])>0})
        cohorts.sort(key=lambda x:(x["avg_net_bps"],x["n"]),reverse=True)
        stable=[x for x in cohorts if x["n"]>=50 and x["stable_positive"]]
        out={"schema":"adaptive_event_engine_v1","research_only":True,"real_orders":False,
             "rows":len(rows),"train_rows":cut,"test_rows":len(rows)-cut,"cost_floor_bps":COST,
             "thresholds":t,"calibration":{"%s|%s"%(k[0],k[1]):v for k,v in c.items()},"cohorts":cohorts,
             "stable_positive":stable[:20],"status":"NO_PROMOTION"}
    OUT.write_text(json.dumps(out,indent=2))
    print(json.dumps({"status":out["status"],"rows":out["rows"],"cohorts":len(out.get("cohorts",[])),
      "stable_positive":len(out.get("stable_positive",[])),"top":out.get("cohorts",[])[:8]},indent=2))

if __name__=="__main__": main()
