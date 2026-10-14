"""Research-only out-of-sample IC and conditional markout benchmark.

Consumes session-tagged feature-tape JSONL; never places orders or mutates strategy.
Reports Spearman IC against future 15s mid returns, L1/flow baselines, and
conditional directional markout at 1/5/15/30/60s for threshold-crossing snapshots.
This is opportunity analysis, NOT a fill simulator: no queue/fill probability.
"""
from __future__ import annotations
import argparse, json, math, statistics
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
HORIZONS=(1,5,15,30,60)
FEATURES=("microprice_imbalance_n","l1_imbalance","signed_flow_1s",
          "delta_bid_replenishment_rate_200ms","binance_imbalance_5",
          "delta_imbalance_5","binance_minus_delta_imbalance","depth_imbalance_covariance_2h",
          "depth_imbalance_correlation_2h","vpin")


def rank(values):
    order=sorted(range(len(values)),key=lambda i: values[i])
    out=[0.0]*len(values); i=0
    while i<len(order):
        j=i+1
        while j<len(order) and values[order[j]]==values[order[i]]: j+=1
        avg=((i+1)+j)/2.0
        for k in order[i:j]: out[k]=avg
        i=j
    return out


def corr(x,y):
    if len(x)<3 or len(x)!=len(y): return None
    rx,ry=rank(x),rank(y)
    mx,my=statistics.fmean(rx),statistics.fmean(ry)
    dx=[v-mx for v in rx]; dy=[v-my for v in ry]
    den=math.sqrt(sum(v*v for v in dx)*sum(v*v for v in dy))
    return sum(a*b for a,b in zip(dx,dy))/den if den else None


def approx_p_two_sided(r,n):
    if r is None or n<3: return None
    if abs(r)>=1: return 0.0
    # Large-sample normal approximation to Spearman's t statistic.
    t=abs(r)*math.sqrt(max(0,n-2)/max(1e-15,1-r*r))
    z=t
    return min(1.0, math.erfc(z/math.sqrt(2)))


def load(path):
    rows=[]
    if not path.exists(): return rows
    with path.open(encoding="utf-8") as f:
        for line in f:
            try:
                r=json.loads(line)
                if r.get("microprice_method") != "price_distance_decay_v1" and r.get("schema") != "cross_venue_depth_toxicity_v1": continue
                ts=float(r.get("ts",r.get("ts_epoch")))
                mid=float(r["mid"])
                if mid>0 and math.isfinite(ts) and math.isfinite(mid): rows.append(r|{"_ts":ts,"_mid":mid})
            except (ValueError,TypeError,KeyError,json.JSONDecodeError): pass
    rows.sort(key=lambda r:r["_ts"])
    return rows


def nearest_future(rows, idx, horizon):
    base=rows[idx]; target=base["_ts"]+horizon
    sid=base.get("session_id","UNSCOPED")
    for j in range(idx+1,len(rows)):
        r=rows[j]
        if r.get("session_id","UNSCOPED") != sid: continue
        if r["_ts"]>=target:
            # Avoid labeling against a quote that is too far beyond target.
            if r["_ts"]-target > 1.5: return None
            return r
    return None


def value(row,key):
    try:
        x=float(row[key])
        return x if math.isfinite(x) else None
    except (TypeError,ValueError,KeyError): return None


def hac_spearman_t(x, y, max_lags=None):
    """Newey-West HAC t-statistic for Spearman IC via standardized-rank regression."""
    n=len(x)
    if n < 8 or n != len(y): return None, None, None
    rx,ry=rank(x),rank(y)
    mx,my=statistics.fmean(rx),statistics.fmean(ry)
    sx=statistics.stdev(rx); sy=statistics.stdev(ry)
    if sx==0 or sy==0: return None, None, None
    zx=[(v-mx)/sx for v in rx]; zy=[(v-my)/sy for v in ry]
    sxx=sum(v*v for v in zx)
    beta=sum(a*b for a,b in zip(zx,zy))/sxx
    residual=[b-beta*a for a,b in zip(zx,zy)]
    scores=[a*e for a,e in zip(zx,residual)]
    if max_lags is None:
        max_lags=min(n-1, max(0, int(4*(n/100.0)**(2/9))))
    max_lags=max(0,min(int(max_lags),n-1))
    long_run=sum(v*v for v in scores)
    for lag in range(1,max_lags+1):
        gamma=sum(scores[t]*scores[t-lag] for t in range(lag,n))
        weight=1.0-lag/(max_lags+1.0)
        long_run += 2.0*weight*gamma
    variance=max(0.0,long_run)/(sxx*sxx)
    se=math.sqrt(variance)
    tstat=beta/se if se>0 else None
    p=math.erfc(abs(tstat)/math.sqrt(2)) if tstat is not None else None
    return tstat,p,max_lags


def quintile_profile(observations, feature="microprice_imbalance_n"):
    pairs=sorted([(value(r,feature),r["target_15s_bps"]) for r in observations
                  if value(r,feature) is not None], key=lambda pair:pair[0])
    n=len(pairs)
    if n<25:
        return {"n":n,"eligible":False,"strictly_monotonic_increasing":False,
                "reason":"need at least 25 holdout labels for five quintiles with five observations each","quintiles":[]}
    quintiles=[]
    for q in range(5):
        lo=q*n//5; hi=(q+1)*n//5
        values=[v for _,v in pairs[lo:hi]]
        quintiles.append({"quintile":q+1,"n":len(values),"mean_forward_15s_return_bps":statistics.fmean(values)})
    means=[q["mean_forward_15s_return_bps"] for q in quintiles]
    return {"n":n,"eligible":True,"strictly_monotonic_increasing":all(means[i]<means[i+1] for i in range(4)),
            "reason":None,"quintiles":quintiles}


def benchmark(rows, holdout_session=None):
    # Unscoped legacy rows are excluded: session boundaries cannot be reconstructed safely.
    groups={}; unscoped_rows_ignored=0
    for r in rows:
        if not r.get("session_id"):
            unscoped_rows_ignored+=1
            continue
        try:
            normalized=r | {"_ts":float(r.get("ts",r.get("ts_epoch"))), "_mid":float(r["mid"])}
        except (TypeError,ValueError,KeyError):
            continue
        groups.setdefault(normalized["session_id"],[]).append(normalized)
    for group in groups.values(): group.sort(key=lambda r:r["_ts"])
    observations=[]
    markouts={h:[] for h in HORIZONS}
    for sid,group in groups.items():
        # IC labels use non-overlapping 15-second anchors to reduce overlap bias.
        next_ic_anchor=float("-inf")
        for i,row in enumerate(group):
            if row["_ts"] < next_ic_anchor: continue
            fut15=nearest_future(group,i,15)
            if fut15:
                target=10000*math.log(fut15["_mid"]/row["_mid"])
                obs={"session_id":sid,"ts":row["_ts"],"target_15s_bps":target}
                for f in FEATURES: obs[f]=value(row,f)
                observations.append(obs)
                next_ic_anchor=row["_ts"]+15.0
        # Markouts use threshold transitions, not every repeated above-threshold row.
        previous_signal=0
        for i,row in enumerate(group):
            signal=int(row.get("microprice_direction",0)) if row.get("microprice_threshold_pass") else 0
            crossing=signal if signal in (-1,1) and signal!=previous_signal else 0
            previous_signal=signal
            if not crossing: continue
            direction=crossing
            for h in HORIZONS:
                future=nearest_future(group,i,h)
                if not future: continue
                entry=value(row,"bid") if direction>0 else value(row,"ask")
                exit_px=value(future,"bid") if direction>0 else value(future,"ask")
                if entry is None or exit_px is None or entry<=0 or exit_px<=0: continue
                quote_to_quote=direction*10000*math.log(exit_px/entry)
                mid_move=direction*10000*math.log(future["_mid"]/row["_mid"])
                markouts[h].append({"session_id":sid,"direction":direction,
                    "markout_bps":quote_to_quote,"directional_mid_move_bps":mid_move,
                    "spread_bps":value(row,"spread_bps"),"signal_ts":row["_ts"]})
    def calc_ics(obs):
        result={}
        for feat in FEATURES:
            pair=[(value(r,feat),r["target_15s_bps"]) for r in obs if value(r,feat) is not None]
            x=[p[0] for p in pair]; y=[p[1] for p in pair]; ic=corr(x,y)
            pv=approx_p_two_sided(ic,len(pair))
            hac_t,hac_p,hac_lags=hac_spearman_t(x,y)
            result[feat]={"n":len(pair),"spearman_ic":ic,"naive_approx_p_two_sided":pv,
                "hac_t_statistic":hac_t,"hac_approx_p_two_sided":hac_p,"hac_lags":hac_lags,
                "passes_ic_0_05_and_hac_t_2_57":bool(len(pair)>=30 and ic is not None and ic>0.05 and hac_t is not None and hac_t>=2.57 and hac_p is not None and hac_p<0.01)}
        return result
    ics=calc_ics(observations)
    if holdout_session is None and groups:
        holdout_session=max(groups,key=lambda sid:max(x["_ts"] for x in groups[sid]))
    elif holdout_session not in groups:
        holdout_session=None
    holdout_obs=[r for r in observations if r["session_id"]==holdout_session]
    holdout_ics=calc_ics(holdout_obs)
    holdout_quintiles=quintile_profile(holdout_obs)
    session_ics={}
    for sid in groups:
        session_ics[sid]=calc_ics([r for r in observations if r["session_id"]==sid])
    delta=None
    a,b=holdout_ics["microprice_imbalance_n"]["spearman_ic"],holdout_ics["l1_imbalance"]["spearman_ic"]
    if a is not None and b is not None: delta=a-b
    marks={}
    for h,items in markouts.items():
        vals=[x["markout_bps"] for x in items]
        marks[str(h)+"s"]={"n":len(vals),"mean_directional_quote_markout_bps":statistics.fmean(vals) if vals else None,
             "median_directional_quote_markout_bps":statistics.median(vals) if vals else None,
             "positive_pct":100*sum(v>0 for v in vals)/len(vals) if vals else None,
             "note":"Quote-to-quote directional markout from best bid/ask entry to future same-side exit quote, before fees; conditional opportunity only, not actual passive fills. Queue position and fill probability unknown."}
    sessions={s:sum(1 for r in observations if r["session_id"]==s) for s in groups}
    return {"schema":"microprice_ic_markout_benchmark_v1","mode":"OFFLINE_RESEARCH_ONLY",
       "rows_loaded":len(rows),"unscoped_legacy_rows_ignored":unscoped_rows_ignored,
       "session_count":len(groups),"labeled_15s_rows":len(observations),
       "session_labeled_rows":sessions,"pooled_predictor_ic_descriptive_only":ics,
       "per_session_predictor_ic":session_ics,"holdout_session_id":holdout_session,
       "holdout_labeled_15s_rows":len(holdout_obs),"holdout_predictor_ic":holdout_ics,
       "holdout_microprice_quintile_profile":holdout_quintiles,
       "holdout_microprice_minus_l1_ic":delta,
       "holdout_incremental_ic_pass_delta_gt_0_03":bool(delta is not None and delta>0.03),
       "holdout_caution":"Newest session is a provisional holdout only; freeze feature/threshold choices before using it for inference.",
       "threshold_markout":marks,"p_value_note":"Promotion IC gate uses Newey-West HAC t-statistics on standardized ranks, requiring n>=30, IC>0.05, HAC t>=2.57 and approximate p<0.01. Five-quintile monotonicity requires >=25 holdout labels. These are still research screens; use session/block bootstrap or permutation inference across independent sessions before promotion.",
       "real_orders":False,"production_changes":False}


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--input",default=str(ROOT/"data/processed/live_microstructure_features_v1.jsonl"))
    ap.add_argument("--output",default=str(ROOT/"data/processed/microprice_ic_markout_benchmark_v1.json"))
    ap.add_argument("--holdout-session",default=None)
    a=ap.parse_args(); rows=load(Path(a.input)); report=benchmark(rows,a.holdout_session)
    out=Path(a.output); out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2,allow_nan=False),encoding="utf-8")
    print(json.dumps(report,indent=2,allow_nan=False))
if __name__=="__main__": main()
