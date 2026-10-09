"""Event-conditioned BTC microstructure edge discovery. Research-only; no execution authority.
Uses contemporaneous features only for event selection and chronological train/test splits.
"""
from __future__ import annotations
import json, math, statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
LAB=ROOT/"data/processed/live_microstructure_labeled_v1.jsonl"
OUT=ROOT/"data/processed/event_conditioned_edge_tournament_v1.json"
COST_BPS=10.76
HORIZONS=(60,120,180,300)

def num(x):
    try:
        v=float(x); return v if math.isfinite(v) else None
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

def f(r,k): return num(r.get(k))

def event_flags(r, thresholds):
    imb=f(r,"imb5"); d5=f(r,"delta5"); d30=f(r,"delta30"); ret5=f(r,"ret5"); ret30=f(r,"ret30")
    if None in (imb,d5,d30,ret5,ret30): return {}
    q=thresholds
    return {
      "FLOW_PRICE_CONFIRM_LONG": d30>=q["d30_hi"] and ret30>=q["ret30_hi"] and imb>=q["imb_hi"],
      "FLOW_PRICE_CONFIRM_SHORT": d30<=q["d30_lo"] and ret30<=q["ret30_lo"] and imb<=q["imb_lo"],
      "ABSORPTION_LONG": d30>=q["d30_hi"] and abs(ret30)<=q["ret30_abs"],
      "ABSORPTION_SHORT": d30<=q["d30_lo"] and abs(ret30)<=q["ret30_abs"],
      "SWEEP_RECLAIM_LONG": ret5<=q["ret5_lo"] and ret30>=0 and imb>=q["imb_hi"],
      "SWEEP_RECLAIM_SHORT": ret5>=q["ret5_hi"] and ret30<=0 and imb<=q["imb_lo"],
      "DIVERGENCE_LONG": d30>=q["d30_hi"] and ret30<=q["ret30_lo"],
      "DIVERGENCE_SHORT": d30<=q["d30_lo"] and ret30>=q["ret30_hi"],
      "IMBALANCE_REVERSAL_LONG": imb>=q["imb_hi"] and d5>=q["d5_hi"] and ret5>=0,
      "IMBALANCE_REVERSAL_SHORT": imb<=q["imb_lo"] and d5<=q["d5_lo"] and ret5<=0,
    }

def thresholds(train):
    def q(key,p):
        vals=[v for v in (f(r,key) for r in train) if v is not None]
        return statistics.quantiles(vals,n=100,method="inclusive")[p-1] if len(vals)>=20 else 0.0
    vals={}
    vals["imb_hi"]=q("imb5",75); vals["imb_lo"]=q("imb5",25)
    vals["d30_hi"]=q("delta30",75); vals["d30_lo"]=q("delta30",25)
    vals["d5_hi"]=q("delta5",75); vals["d5_lo"]=q("delta5",25)
    vals["ret30_hi"]=q("ret30",75); vals["ret30_lo"]=q("ret30",25)
    vals["ret5_hi"]=q("ret5",75); vals["ret5_lo"]=q("ret5",25)
    vals["ret30_abs"]=max(abs(vals["ret30_hi"]),abs(vals["ret30_lo"]))*0.35
    return vals

def evaluate(rows):
    if len(rows)<200: return {"error":"insufficient_rows","rows":len(rows)}
    cut=int(len(rows)*0.60)
    train=rows[:cut]; test=rows[cut:]
    th=thresholds(train)
    results=[]
    for h in HORIZONS:
        for r in test:
            labs=r.get("labels",{}); lab=labs.get(str(h),{})
            y=num(lab.get("move_bps")) if isinstance(lab,dict) else None
            if y is None: continue
            flags=event_flags(r,th)
            for name,hit in flags.items():
                if not hit: continue
                side=1 if name.endswith("LONG") else -1
                results.append((h,name,side*y,float(r["ts"])))
    out=[]
    for h in HORIZONS:
        for name in sorted({x[1] for x in results if x[0]==h}):
            ys=[x[2] for x in results if x[0]==h and x[1]==name]
            if len(ys)<30: continue
            mid=len(ys)//2
            gross=statistics.fmean(ys); net=gross-COST_BPS
            first=statistics.fmean(ys[:mid])-COST_BPS; second=statistics.fmean(ys[mid:])-COST_BPS
            wins=sum(y>0 for y in ys); losses=sum(y<0 for y in ys)
            gp=sum(y for y in ys if y>0); gl=-sum(y for y in ys if y<0)
            out.append({"horizon_s":h,"event":name,"n":len(ys),"gross_avg_bps":gross,
              "net_avg_bps":net,"first_half_net_bps":first,"second_half_net_bps":second,
              "positive_rate":wins/len(ys),"profit_factor":gp/gl if gl else None,
              "stable_positive":net>0 and first>0 and second>0})
    out.sort(key=lambda x:(x["net_avg_bps"],x["n"]),reverse=True)
    stable=[x for x in out if x["n"]>=50 and x["stable_positive"]]
    return {"schema":"event_conditioned_edge_tournament_v1","research_only":True,
      "real_orders":False,"rows_loaded":len(rows),"train_rows":len(train),"test_rows":len(test),
      "cost_floor_bps":COST_BPS,"thresholds_derived_from_train_only":True,
      "results":out,"stable_positive":stable[:30]}

def main():
    result=evaluate(load())
    OUT.write_text(json.dumps(result,indent=2))
    print(json.dumps({"rows_loaded":result.get("rows_loaded"),"results":len(result.get("results",[])),
      "stable_positive":len(result.get("stable_positive",[])),"top":result.get("results",[])[:10]},indent=2))

if __name__=="__main__": main()
