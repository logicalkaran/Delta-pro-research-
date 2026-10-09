"""Causal walk-forward forecast calibration v2. Research/paper only.

Purpose:
- remove duplicate strategy labels at the same timestamp/horizon
- use chronological walk-forward scoring
- embargo overlapping future-label windows
- never authorize production or exchange orders
"""
from collections import defaultdict
from pathlib import Path
import json, math, time

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"data/processed/strategy_forward_tournament_v1.jsonl"
OUT=ROOT/"data/processed/causal_forecast_calibration_v2.json"
MIN_TRAIN=40
EMBARGO_S=300
FOLDS=5

def load():
    rows=[]
    if not SRC.exists(): return rows
    for line in SRC.read_text().splitlines():
        try:
            r=json.loads(line)
            t=float(r.get("issued_at",0)); h=int(r.get("horizon",0))
            if t>0 and h in (1,2,3,5) and r.get("net_return_pct") is not None:
                rows.append(r)
        except Exception:
            pass
    # One outcome per timestamp/horizon. Strategy labels are not independent observations.
    uniq={}
    for r in rows:
        k=(float(r["issued_at"]),int(r["horizon"]))
        uniq.setdefault(k,r)
    return sorted(uniq.values(),key=lambda r:float(r["issued_at"]))

def bucket(x,cuts):
    x=float(x)
    for i,c in enumerate(cuts):
        if x<c: return i
    return len(cuts)

def key(r):
    d=float(r.get("delta5",0)); i=float(r.get("imbalance",0)); q=float(r.get("return5",0))
    return (
        int(r.get("horizon",0)),
        str(r.get("regime","?")),
        bucket(d,(-.30,-.15,-.05,.05,.15,.30)),
        bucket(i,(-.60,-.30,-.10,.10,.30,.60)),
        bucket(q,(-.15,-.05,-.02,.02,.05,.15)),
    )

def add(store,r):
    x=store[key(r)]
    y=float(r["net_return_pct"])*100
    x[0]+=1; x[1]+=y; x[2]+=y*y; x[3]+=1 if y>0 else 0

def predict(store,r):
    x=store.get(key(r))
    if not x or x[0]<MIN_TRAIN: return None
    n,total,sq,w=x
    m=total/n
    var=max(0.0,sq/n-m*m)
    se=math.sqrt(var/n) if n>1 else 1e9
    return m-1.28*se

def metrics(scored):
    if not scored: return {"samples":0}
    ys=[y for _,y in scored]; ps=[p for p,_ in scored]
    n=len(ys)
    mae=sum(abs(p-y) for p,y in scored)/n
    xp=sum(ps)/n; yp=sum(ys)/n
    num=sum((p-xp)*(y-yp) for p,y in scored)
    dx=sum((p-xp)**2 for p in ps); dy=sum((y-yp)**2 for y in ys)
    corr=num/math.sqrt(dx*dy) if dx and dy else None
    positive=sum(y>0 for y in ys)/n
    avg=sum(ys)/n
    return {"samples":n,"mae_bps":mae,"correlation":corr,"avg_actual_net_bps":avg,"positive_rate":positive}

def main():
    rows=load()
    n=len(rows)
    if n<100:
        out={"status":"INSUFFICIENT_DATA","unique_rows":n,"paper_only":True,"real_orders":False,"promotion_allowed":False}
        OUT.write_text(json.dumps(out,indent=2)); print(json.dumps(out,indent=2)); return

    # Chronological fold boundaries. Training is strictly before the test window.
    fold_results=[]
    all_scored=[]
    for fold in range(1,FOLDS+1):
        test_start=int(n*fold/FOLDS)-int(n/FOLDS)
        test_end=int(n*fold/FOLDS)
        train_end=test_start
        test=rows[test_start:test_end]
        if not test: continue
        cutoff=float(test[0]["issued_at"])-EMBARGO_S
        train=[r for r in rows[:train_end] if float(r["issued_at"])+int(r.get("horizon",0))*60 <= cutoff]
        store=defaultdict(lambda:[0,0.,0.,0])
        for r in train: add(store,r)
        scored=[]
        for r in test:
            p=predict(store,r)
            if p is not None:
                scored.append((p,float(r["net_return_pct"])*100))
        all_scored.extend(scored)
        m=metrics(scored)
        m.update({"fold":fold,"train_rows":len(train),"test_rows":len(test)})
        fold_results.append(m)

    overall=metrics(all_scored)
    # Conservative selection diagnostic: only retain forecasts whose lower confidence estimate is positive.
    for extra in (0,2,4,8):
        z=[y for p,y in all_scored if p>extra]
        overall[f"select_gt_{extra}bps"]={
            "samples":len(z),
            "avg_actual_net_bps":sum(z)/len(z) if z else None,
            "positive_rate":sum(y>0 for y in z)/len(z) if z else None
        }

    out={
        "updated_at":time.time(),
        "status":"RESEARCH_ONLY",
        "source_rows":sum(1 for _ in SRC.open()) if SRC.exists() else 0,
        "unique_timestamp_horizon_rows":n,
        "overall":overall,
        "folds":fold_results,
        "method":{
            "features":["horizon","regime","delta5","imbalance","return5"],
            "unique_key":"issued_at+horizon",
            "min_train_per_bucket":MIN_TRAIN,
            "walk_forward_folds":FOLDS,
            "embargo_seconds":EMBARGO_S,
            "shrinkage_z":1.28,
            "duplicate_strategy_labels_removed":True,
            "paper_only":True,
            "real_orders":False,
            "promotion_allowed":False
        }
    }
    OUT.write_text(json.dumps(out,indent=2))
    print(json.dumps({"unique_rows":n,"overall":overall,"folds":fold_results},indent=2))

if __name__=="__main__":
    main()
