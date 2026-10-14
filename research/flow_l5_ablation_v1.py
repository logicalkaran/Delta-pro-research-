"""Leakage-aware ablation: signed-flow proxy vs flow + L5 imbalance on saved labelled snapshots.
Research-only. Does not import production trading/execution modules or place orders.
"""
from __future__ import annotations
import hashlib, json, math
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"data/processed/live_microstructure_labeled_v2.jsonl"
OUT=ROOT/"data/processed/flow_l5_ablation_v1.json"
HORIZONS=(60,120,300)
COST_BPS=14.0  # conservative placeholder used for sensitivity, not verified per-account cost
MIN_TRAIN=250
MIN_TEST=30
SEED=20261012

def read_rows():
    rows=[]
    with SOURCE.open(encoding="utf-8") as f:
        for line_no,line in enumerate(f,1):
            try:
                r=json.loads(line); ts=float(r["ts"]); mid=float(r["mid"])
                if not math.isfinite(ts) or not math.isfinite(mid) or mid<=0: continue
                labels=r.get("labels",{})
                clean={"ts":ts,"mid":mid,"delta30":float(r["delta30"]),
                       "imb5":float(r["imb5"]),"fresh":float(r.get("fresh",999)),
                       "session_id":r.get("session_id")}
                if not all(math.isfinite(clean[k]) for k in ("delta30","imb5","fresh")): continue
                clean["labels"]={}
                for h in HORIZONS:
                    z=labels.get(str(h),{})
                    if isinstance(z,dict):
                        try:
                            ft=float(z["future_ts"]); mv=float(z["move_bps"])
                            if math.isfinite(ft) and math.isfinite(mv) and ft>ts and ft-ts <= h+3:
                                clean["labels"][h]={"future_ts":ft,"move_bps":mv}
                        except (KeyError,TypeError,ValueError): pass
                if clean["labels"]: rows.append(clean)
            except (ValueError,TypeError,KeyError): continue
    rows.sort(key=lambda r:r["ts"])
    # Same-timestamp duplicates are ambiguous; keep first deterministically.
    out=[]; seen=set()
    for r in rows:
        if r["ts"] not in seen: out.append(r); seen.add(r["ts"])
    return out

def fit(X,y,steps=900,lr=.04,l2=.1):
    mu=X.mean(0); sd=X.std(0); sd[sd<1e-8]=1.
    Z=np.clip((X-mu)/sd,-12,12)
    rate=float(np.clip(y.mean(),.01,.99)); w=np.zeros(X.shape[1]); b=math.log(rate/(1-rate))
    for _ in range(steps):
        p=1/(1+np.exp(-np.clip(Z@w+b,-30,30)))
        w-=lr*((Z.T@(p-y))/len(y)+l2*w); b-=lr*float(np.mean(p-y))
    return mu,sd,w,b

def predict(m,X):
    mu,sd,w,b=m
    return 1/(1+np.exp(-np.clip(((X-mu)/sd)@w+b,-30,30)))

def metrics(y,p):
    q=np.clip(p,1e-7,1-1e-7)
    return {"n":int(len(y)),"brier":float(np.mean((p-y)**2)),
            "log_loss":float(-np.mean(y*np.log(q)+(1-y)*np.log(1-q))),
            "accuracy_at_0_5":float(np.mean((p>=.5)==y))}

def select_nonoverlap(rows,horizon):
    eligible=[r for r in rows if horizon in r["labels"] and r["fresh"]<=2]
    chosen=[]; last_target=-float("inf")
    for r in eligible:
        label=r["labels"][horizon]
        if r["ts"] < last_target: continue
        chosen.append({**r,"future_ts":label["future_ts"],"move_bps":label["move_bps"],
                       "y":float(label["move_bps"]>0)})
        last_target=label["future_ts"]
    return chosen

def evaluate_horizon(rows,horizon):
    events=select_nonoverlap(rows,horizon); n=len(events)
    if n < MIN_TRAIN+MIN_TEST:
        return {"horizon_seconds":horizon,"decision":"NEED_MORE_DATA","events":n,
                "reason":"Insufficient non-overlapping, fresh observations"}
    starts=[int(n*.4),int(n*.6),int(n*.8)]; ends=[int(n*.6),int(n*.8),n]
    folds=[]; pooled={"flow_only":[],"flow_plus_imb5":[]}
    for fold,(a,b) in enumerate(zip(starts,ends),1):
        test=events[a:b]; test_start=test[0]["ts"]
        train=[r for r in events[:a] if r["future_ts"] < test_start]
        if len(train)<MIN_TRAIN or len(test)<MIN_TEST:
            folds.append({"fold":fold,"status":"NEED_MORE_DATA","train_n":len(train),"test_n":len(test)}); continue
        ytr=np.array([r["y"] for r in train]); yte=np.array([r["y"] for r in test])
        Xtr0=np.array([[r["delta30"]] for r in train]); Xte0=np.array([[r["delta30"]] for r in test])
        Xtr1=np.array([[r["delta30"],r["imb5"]] for r in train]); Xte1=np.array([[r["delta30"],r["imb5"]] for r in test])
        p0=predict(fit(Xtr0,ytr),Xte0); p1=predict(fit(Xtr1,ytr),Xte1)
        # Threshold is fixed ex ante. Trade only at >=55% or <=45%; all returns measured net of cost.
        def trade(p):
            pos=np.where(p>=.55,1.,np.where(p<=.45,-1.,0.))
            active=pos!=0
            gross=pos[active]*np.array([r["move_bps"] for r in test])[active]
            net=gross-COST_BPS
            return {"signals":int(active.sum()),"coverage":float(active.mean()),
                    "mean_gross_bps":float(gross.mean()) if len(gross) else None,
                    "mean_net_bps":float(net.mean()) if len(net) else None,
                    "positive_net_fraction":float((net>0).mean()) if len(net) else None}
        m0,m1=metrics(yte,p0),metrics(yte,p1)
        t0,t1=trade(p0),trade(p1)
        folds.append({"fold":fold,"train_n":len(train),"test_n":len(test),
            "train_start_ts":train[0]["ts"],"train_end_ts":train[-1]["ts"],
            "test_start_ts":test[0]["ts"],"test_end_ts":test[-1]["ts"],
            "test_positive_rate":float(yte.mean()),"flow_only":m0,
            "flow_plus_imb5":m1,"brier_improvement":m0["brier"]-m1["brier"],
            "flow_only_fixed_threshold_trade":t0,"flow_plus_imb5_fixed_threshold_trade":t1})
        for name,vals in (("flow_only",t0),("flow_plus_imb5",t1)):
            if vals["mean_net_bps"] is not None: pooled[name].append(vals["mean_net_bps"])
    good=[f for f in folds if f.get("status") is None]
    improvements=[f["brier_improvement"] for f in good]
    if len(good)<3: decision="NEED_MORE_DATA"
    elif all(x>0 for x in improvements) and all(f["flow_plus_imb5_fixed_threshold_trade"]["mean_net_bps"] is not None and f["flow_plus_imb5_fixed_threshold_trade"]["mean_net_bps"]>0 for f in good): decision="PROVISIONAL_SHADOW_CANDIDATE"
    elif all(x<=0 for x in improvements): decision="NO_INCREMENTAL_CALIBRATION_EDGE"
    else: decision="INCONCLUSIVE"
    return {"horizon_seconds":horizon,"decision":decision,"non_overlapping_events":n,
        "folds":folds,"mean_fold_brier_improvement":float(np.mean(improvements)) if improvements else None,
        "mean_fold_net_bps_by_model":{k:float(np.mean(v)) if v else None for k,v in pooled.items()},
        "cost_assumption_bps":COST_BPS}

def run():
    rows=read_rows()
    source_hash=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    report={"experiment":"FLOW_PLUS_L5_IMBALANCE_ABLATION_V1",
        "created_at_utc":datetime.now(timezone.utc).isoformat(),"source":str(SOURCE.relative_to(ROOT)),
        "source_sha256":source_hash,"raw_rows_valid":len(rows),
        "timestamp_range_utc":[datetime.fromtimestamp(rows[0]["ts"],timezone.utc).isoformat(),
                               datetime.fromtimestamp(rows[-1]["ts"],timezone.utc).isoformat()] if rows else None,
        "freshness_gate_seconds":2,"label_horizons_seconds":list(HORIZONS),
        "hypothesis":"Adding 5-level book imbalance (imb5) to the signed-flow proxy (delta30) improves out-of-sample probability quality and net outcomes over flow alone.",
        "validation":"Three expanding chronological folds; train labels must mature before test start; observations are selected so label windows do not overlap; fixed 45/55 probability thresholds; scaling fit on train only.",
        "results":[evaluate_horizon(rows,h) for h in HORIZONS],
        "data_quality":{"all_rows_require_freshness_le_2s":True,"source_rows_missing_session_id":sum(not r.get("session_id") for r in rows),
            "note":"Rows without session_id are retained only when source timestamps and labels are valid; large timestamp gaps can still mix sessions. Treat findings as exploratory until session boundaries are independently verified."},
        "limitations":["delta30 is a signed-flow proxy, not raw event-level signed trades.",
            "imb5 is a saved state feature; not proof of historical order-book event continuity.",
            "14 bps is a conservative placeholder cost, not account-specific verified fees/fills.",
            "No conformal model fitting, NLP shock labels, queue-aware fills, or formal Deflated Sharpe Ratio in this ablation.",
            "No production logic, risk settings, promotion thresholds, or order routes are touched."],
        "policy":{"research_only":True,"production_logic_changed":False,"risk_limits_changed":False,"real_orders":False}}
    tmp=OUT.with_suffix(".json.tmp"); tmp.write_text(json.dumps(report,indent=2,allow_nan=False)); tmp.replace(OUT)
    print(json.dumps({"output":str(OUT),"source_sha256":source_hash,"valid_rows":len(rows),
        "results":[{"horizon_seconds":x["horizon_seconds"],"decision":x["decision"],
                    "events":x["non_overlapping_events"] if "non_overlapping_events" in x else x.get("events"),
                    "mean_fold_brier_improvement":x.get("mean_fold_brier_improvement"),
                    "mean_fold_net_bps_by_model":x.get("mean_fold_net_bps_by_model")} for x in report["results"]],
        "research_only":True,"real_orders":False},indent=2))
if __name__=="__main__": run()
