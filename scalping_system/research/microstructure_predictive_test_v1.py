#!/usr/bin/env python3
"""Leakage-safe microstructure predictive-value test. Research only."""
import json, math
from pathlib import Path

SRC=Path("data/processed/strategy_forward_tournament_v1.jsonl")
OUT=Path("data/processed/microstructure_predictive_test_v1.json")
FEATURES=["delta5","delta30","imbalance","return5"]
MIN_TRAIN=200
MIN_TEST=100
TRAIN_FRAC=0.70
NET_COST_PCT=0.12

def pf(xs):
    pos=sum(x for x in xs if x>0); neg=-sum(x for x in xs if x<0)
    return pos/neg if neg else (float("inf") if pos else 0.0)

rows=[]
with SRC.open() as f:
    for line in f:
        if line.strip():
            try:
                r=json.loads(line);
                if all(k in r for k in FEATURES) and "net_return_pct" in r: rows.append(r)
            except Exception: pass
rows.sort(key=lambda r:r.get("issued_at",0))
cut=int(len(rows)*TRAIN_FRAC)
train,test=rows[:cut],rows[cut:]

def eval_group(rs):
    ys=[float(r["net_return_pct"]) for r in rs]
    return {"n":len(ys),"avg_net_bps":sum(ys)/len(ys)*100 if ys else 0,
            "win_rate":sum(y>0 for y in ys)/len(ys) if ys else 0,
            "profit_factor":pf(ys)}

def candidate_thresholds(vals):
    vals=sorted(vals)
    if not vals: return []
    qs=[.1,.2,.3,.4,.5,.6,.7,.8,.9]
    return [vals[min(len(vals)-1,max(0,int(q*(len(vals)-1))))] for q in qs]

results=[]
for feat in FEATURES:
    # Thresholds are selected from TRAIN ONLY.
    thresholds=candidate_thresholds([float(r[feat]) for r in train])
    for side in ["LONG","SHORT"]:
        for thr in thresholds:
            def filt(rs):
                if side=="LONG": return [r for r in rs if float(r[feat])>=thr]
                return [r for r in rs if float(r[feat])<=thr]
            a,b=filt(train),filt(test)
            if len(a)<MIN_TRAIN or len(b)<MIN_TEST: continue
            ea,eb=eval_group(a),eval_group(b)
            results.append({"feature":feat,"side":side,"threshold":thr,
                            "train":ea,"test":eb,
                            "stable_positive":ea["avg_net_bps"]>0 and eb["avg_net_bps"]>0,
                            "stable_pf":ea["profit_factor"]>=1.2 and eb["profit_factor"]>=1.2})

stable=[x for x in results if x["stable_positive"] and x["stable_pf"]]
stable.sort(key=lambda x:(x["test"]["avg_net_bps"],x["test"]["profit_factor"]),reverse=True)

# Also report unconditional feature correlation with next outcome.
cor=[]
for feat in FEATURES:
    pairs=[(float(r[feat]),float(r["net_return_pct"])*100) for r in rows]
    n=len(pairs)
    mx=sum(x for x,y in pairs)/n; my=sum(y for x,y in pairs)/n
    denx=math.sqrt(sum((x-mx)**2 for x,y in pairs)); deny=math.sqrt(sum((y-my)**2 for x,y in pairs))
    corr=sum((x-mx)*(y-my) for x,y in pairs)/(denx*deny) if denx and deny else 0
    cor.append({"feature":feat,"pearson_corr":corr})

out={"status":"NO_STABLE_EDGE" if not stable else "STABLE_CANDIDATES_FOUND",
     "source_rows":len(rows),"train_rows":len(train),"test_rows":len(test),
     "chronological_split":TRAIN_FRAC,"net_cost_pct":NET_COST_PCT,
     "method":"thresholds selected on train only; evaluated on untouched chronological test; research-only",
     "features":FEATURES,"stable_candidates":stable[:10],"feature_correlations":cor,
     "auto_apply":False,"paper_only":True,"real_orders":False}
OUT.write_text(json.dumps(out,indent=2))
print(json.dumps({"status":out["status"],"rows":len(rows),"stable":len(stable),"top":stable[:3],"corr":cor},indent=2))
