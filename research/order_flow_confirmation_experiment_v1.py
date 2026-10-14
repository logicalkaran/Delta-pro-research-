"""Research-only BTC perpetual order-flow confirmation experiment; never places orders."""
from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
TAPE = ROOT / "data/processed/live_microstructure_features_v1.jsonl"
OUT = ROOT / "data/processed/order_flow_confirmation_experiment_v1.json"
HORIZON_S = 5.0
MAX_LATENESS_S = 2.0
MAX_STATE_AGE_S = 2.0
MIN_EVENTS = 300
BASE_COST_BPS = 14.0  # placeholder, not verified Delta fee schedule
EXTRA_SLIPPAGE_BPS = 5.0
SEED = 20261010

def load_rows():
    rows = []
    with TAPE.open() as f:
        for line in f:
            try:
                r = json.loads(line)
                ts, mid = float(r["ts"]), float(r["mid"])
                age = float(r.get("state_age_s", r.get("fresh", 999)))
                x = [float(r["delta30"]), float(r["imb5"]), float(r["ret5"])]
                if (r.get("session_id") and math.isfinite(ts) and math.isfinite(mid)
                    and mid > 0 and math.isfinite(age) and 0 <= age <= MAX_STATE_AGE_S
                    and all(math.isfinite(v) for v in x)):
                    rows.append((r["session_id"], ts, mid, x, float(r.get("spread_bps", 0))))
            except (ValueError, TypeError, KeyError):
                continue
    rows.sort(key=lambda z: (z[0], z[1]))
    # Deduplicate timestamps within a session.
    out, seen = [], set()
    for r in rows:
        key = (r[0], r[1])
        if key not in seen:
            out.append(r); seen.add(key)
    return out

def make_events(rows):
    # Non-overlapping observation origins >=5s apart within each session.
    by_session = {}
    for r in rows: by_session.setdefault(r[0], []).append(r)
    events = []
    for sid, rr in by_session.items():
        rr.sort(key=lambda z: z[1])
        next_origin = -float("inf")
        j = 0
        for i, r in enumerate(rr):
            if r[1] < next_origin: continue
            target_t = r[1] + HORIZON_S
            while j < len(rr) and rr[j][1] < target_t: j += 1
            if j >= len(rr): continue
            target = rr[j]
            if target[1] - target_t > MAX_LATENESS_S: continue
            # Prevent stale/long holes and require same-session future mid.
            if target[1] <= r[1] or target[1] - r[1] < HORIZON_S: continue
            yret = (target[2] / r[2] - 1.0) * 10000.0
            if not math.isfinite(yret): continue
            events.append({"session_id": sid, "ts": r[1], "mid": r[2],
                "x": r[3], "spread_bps": r[4], "future_bps": yret,
                "y": int(yret > 0), "target_ts": target[1]})
            next_origin = r[1] + HORIZON_S
    return sorted(events, key=lambda e: e["ts"])

def sigmoid(z): return 1/(1+np.exp(-np.clip(z, -30, 30)))

def fit_logistic(X, y, steps=1600, lr=.04, l2=.05):
    mu = X.mean(axis=0); sd = X.std(axis=0); sd[sd < 1e-9] = 1.0
    Z = (X-mu)/sd
    rate = float(np.clip(y.mean(), .01, .99))
    w = np.zeros(Z.shape[1]); b = math.log(rate/(1-rate))
    for _ in range(steps):
        p = sigmoid(Z @ w+b)
        w -= lr*((Z.T@(p-y))/len(y)+l2*w)
        b -= lr*float(np.mean(p-y))
    return mu, sd, w, b

def pmetrics(y,p):
    p=np.clip(np.asarray(p),1e-6,1-1e-6); y=np.asarray(y,dtype=float)
    bins=[]
    for lo in np.arange(0,1,.2):
        m=(p>=lo)&(p<lo+.2 if lo<.8 else p<=1)
        if m.any(): bins.append({"bin":[round(float(lo),1),round(float(lo+.2),1)],"n":int(m.sum()),
            "mean_p":float(p[m].mean()),"observed_rate":float(y[m].mean())})
    return {"n":len(y),"brier":float(np.mean((p-y)**2)),
        "log_loss":float(-np.mean(y*np.log(p)+(1-y)*np.log(1-p))),"calibration_bins":bins}

def tmetrics(net):
    a=np.asarray(net,dtype=float)
    if not len(a): return {"independent_trade_count":0,"mean_net_bps":None,"profit_factor":None,"win_rate":None,"max_drawdown_bps":None}
    wins=a[a>0]; losses=a[a<0]; eq=np.cumsum(a); peak=np.maximum.accumulate(np.r_[0.,eq])[1:]
    return {"independent_trade_count":int(len(a)),"mean_net_bps":float(a.mean()),
      "profit_factor":float(wins.sum()/abs(losses.sum())) if len(losses) and losses.sum()!=0 else None,
      "win_rate":float((a>0).mean()),"max_drawdown_bps":float(np.max(peak-eq))}

def boot(values, block=5, reps=1000):
    a=np.asarray(values,dtype=float)
    if len(a)<30: return {"low_95":None,"high_95":None,"n":len(a),"method":"insufficient independent trades (<30)"}
    rng=np.random.default_rng(SEED); means=[]; n=len(a)
    for _ in range(reps):
        s=[]
        while len(s)<n:
            start=int(rng.integers(0,n))
            s.extend(a[(start+k)%n] for k in range(block))
        means.append(np.mean(s[:n]))
    return {"low_95":float(np.quantile(means,.025)),"high_95":float(np.quantile(means,.975)),
      "n":n,"method":f"circular moving-block bootstrap; block={block}; reps={reps}"}

def run():
    rows=load_rows(); events=make_events(rows)
    if len(events)<MIN_EVENTS:
        result={"experiment":"ORDER_FLOW_CONFIRMATION_5S_V1","decision":"NEED_MORE_DATA",
          "hypothesis":"imb5 adds predictive value beyond delta30 and ret5 for the next 5-second mid-price direction",
          "reason":f"Need >= {MIN_EVENTS} eligible non-overlapping events; found {len(events)}",
          "valid_rows":len(rows),"events":len(events),"data_source":"local microstructure state snapshots, not exchange-native full event stream"}
        OUT.write_text(json.dumps(result,indent=2)); print(json.dumps(result,indent=2)); return
    X=np.asarray([e["x"] for e in events],float); y=np.asarray([e["y"] for e in events],float)
    rets=np.asarray([e["future_bps"] for e in events],float)
    folds=[]; all_net=[]; fold_improvements=[]; fold_means=[]
    # Expanding chronological folds, with 5s label-maturity purge.
    n=len(events); edges=[int(n*.4),int(n*.6),int(n*.8),n]
    starts=[int(n*.4),int(n*.6),int(n*.8)]
    ends=[int(n*.6),int(n*.8),n]
    for k,(a,b) in enumerate(zip(starts,ends),1):
        test_idx=np.arange(a,b)
        test_start=events[a]["ts"]
        train_idx=np.array([i for i in range(a) if events[i]["target_ts"] < test_start])
        if len(train_idx)<100 or len(test_idx)<30:
            folds.append({"fold":k,"decision":"NEED_MORE_DATA","train_n":len(train_idx),"test_n":len(test_idx)}); continue
        mu,sd,w,bias=fit_logistic(X[train_idx],y[train_idx])
        p=sigmoid(((X[test_idx]-mu)/sd)@w+bias)
        # Nested comparator excludes imbalance: delta30 + ret5 only.
        reduced_cols=[0,2]
        mu0,sd0,w0,bias0=fit_logistic(X[train_idx][:,reduced_cols],y[train_idx])
        p_reduced=sigmoid(((X[test_idx][:,reduced_cols]-mu0)/sd0)@w0+bias0)
        base=np.full(len(test_idx),y[train_idx].mean())
        # Directional rules: baseline flow-only, then flow+imbalance confirmation.
        flow=np.sign(X[test_idx,0])
        confirm=np.where(flow*np.sign(X[test_idx,1])>0,flow,0.0)
        gross=rets[test_idx]
        net_flow=flow*gross-BASE_COST_BPS
        net_confirm=confirm*gross-BASE_COST_BPS
        net_confirm_stress=confirm*gross-(BASE_COST_BPS+EXTRA_SLIPPAGE_BPS)
        pm=pmetrics(y[test_idx],p); rm=pmetrics(y[test_idx],p_reduced); bm=pmetrics(y[test_idx],base)
        improvement=rm["brier"]-pm["brier"]; fold_improvements.append(improvement)
        cm=tmetrics(net_confirm[confirm!=0]); fold_means.append(cm["mean_net_bps"])
        folds.append({"fold":k,"train_n":len(train_idx),"test_n":len(test_idx),
          "test_start_ts":test_start,"test_end_ts":events[b-1]["ts"],
          "positive_rate":float(y[test_idx].mean()),"base_rate_baseline":bm,
          "logistic_delta30_ret5_without_imbalance":rm,"logistic_delta30_imb5_ret5":pm,
          "brier_improvement_vs_reduced_model":improvement,
          "flow_only":tmetrics(net_flow[flow!=0]),
          "flow_plus_imbalance_confirmation":cm,
          "confirmation_plus_5bps_slippage":tmetrics(net_confirm_stress[confirm!=0]),
          "cost_assumption_bps":BASE_COST_BPS})
        all_net.extend(net_confirm[confirm!=0].tolist())
    ci=boot(all_net)
    valid_folds=[f for f in folds if "logistic_delta30_imb5_ret5" in f]
    if len(valid_folds)<3 or len(all_net)<30: decision="NEED_MORE_DATA"
    elif ci["high_95"] is not None and ci["high_95"]<0: decision="REJECT"
    elif all(f.get("flow_plus_imbalance_confirmation",{}).get("mean_net_bps", -1)<=0 for f in valid_folds): decision="REJECT"
    elif all(f.get("brier_improvement_vs_reduced_model",0)>0 and f.get("flow_plus_imbalance_confirmation",{}).get("mean_net_bps", -1)>0 for f in valid_folds): decision="SHADOW_ONLY"
    else: decision="NEED_MORE_DATA"
    result={"experiment":"ORDER_FLOW_CONFIRMATION_5S_V1","decision":decision,
      "hypothesis":"At a 5-second horizon, order-book imbalance confirmation adds predictive value beyond signed flow and short-term return.",
      "mechanism":"Persistent aggressive flow aligned with displayed depth may indicate pressure; cancellations, hidden liquidity and adverse selection can invalidate it.",
      "features":["delta30","imb5","ret5"],"horizon_seconds":HORIZON_S,
      "events":len(events),"valid_snapshot_rows":len(rows),"positive_rate":float(y.mean()),
      "data_quality":{"max_state_age_s":MAX_STATE_AGE_S,"max_target_lateness_s":MAX_LATENESS_S,
        "non_overlapping_origins":True,"same_session_only":True,"full_exchange_event_stream":False},
      "costs":{"base_round_trip_bps":BASE_COST_BPS,"stress_extra_slippage_bps":EXTRA_SLIPPAGE_BPS,
        "warning":"14 bps is a placeholder, not verified account fees; no queue-aware fills; mid-price labels are not executable fills."},
      "pooled_confirmation_trades":tmetrics(all_net),"pooled_mean_net_bootstrap_95":ci,
      "folds":folds,"limitations":["Snapshots are not complete L2/trade event history.","Displayed depth may cancel or be spoofed.",
      "No production strategy changes or exchange orders.","Decision is research triage, not trade authorization."]}
    OUT.write_text(json.dumps(result,indent=2)); print(json.dumps(result,indent=2))

if __name__=="__main__": run()
