"""Evidence-calibrated ensemble for BTC scalping research. No execution authority."""
from __future__ import annotations
import json,math,time
from pathlib import Path
from research.pro_scalper_v5 import evaluate as v5_evaluate
ROOT=Path(__file__).resolve().parents[1]
LAB=ROOT/"data/processed/live_microstructure_labeled_v1.jsonl"
NEWS=ROOT/"data/processed/news_momentum_signal.json"
NEWS_STATE=ROOT/"data/processed/news_event_state_v5.json"
MTF=ROOT/"data/processed/multi_timeframe_context_v1.json"
EVENT_EDGE=ROOT/"data/processed/event_conditioned_edge_tournament_v1.json"
COST=ROOT/"research/pro_scalper_v5_config.json"
# Cache the read-only labeled dataset by path, mtime, and size. The paper runner
# calls the ensemble every second; reparsing/sorting this multi-MB file for each
# horizon was wasting CPU without changing the underlying labels.
_ROWS_CACHE_SIGNATURE=None
_ROWS_CACHE=[]
KEYS=("imb5","imb10","delta5","delta30","delta60","ret5","ret30","ret60","cvd_slope30","spread_bps")
SCALE={"imb5":1.0,"imb10":1.0,"delta5":1.0,"delta30":1.0,"delta60":1.0,"ret5":0.05,"ret30":0.1,"ret60":0.1,"cvd_slope30":1000.0,"spread_bps":0.1}

def rows():
    """Return a cached chronological snapshot of labeled rows; refresh on file change."""
    global _ROWS_CACHE_SIGNATURE,_ROWS_CACHE
    try:
        st=LAB.stat()
        signature=(str(LAB.resolve()),st.st_mtime_ns,st.st_size)
    except OSError:
        signature=(str(LAB.resolve()),None,None)
    if signature==_ROWS_CACHE_SIGNATURE:
        return _ROWS_CACHE
    out=[]
    if signature[1] is not None:
        for line in LAB.read_text().splitlines():
            try:
                r=json.loads(line)
                if isinstance(r,dict) and isinstance(r.get("labels"),dict): out.append(r)
            except: pass
    loaded=sorted(out,key=lambda x:float(x.get("ts",0)))
    # Do not cache a partial snapshot if the source changed while it was read.
    try:
        after=LAB.stat()
        stable=(signature[1] is not None and after.st_mtime_ns==signature[1] and after.st_size==signature[2])
    except OSError:
        stable=signature[1] is None
    _ROWS_CACHE=loaded
    _ROWS_CACHE_SIGNATURE=signature if stable else None
    return _ROWS_CACHE

def finite(x):
    try:return math.isfinite(float(x))
    except:return False

def distance(a,b):
    s=0.0;n=0
    for k in KEYS:
        if finite(a.get(k)) and finite(b.get(k)):
            z=(float(a[k])-float(b[k]))/SCALE[k]
            s+=z*z;n+=1
    return math.sqrt(s/n) if n else 99.0

def current_features(state):
    ob=state.get("order_book",{}); w=state.get("windows",{}); p=state.get("price",{})
    mid=float(ob.get("mid_price") or 0); bid=float(ob.get("best_bid") or 0); ask=float(ob.get("best_ask") or 0)
    return {"imb5":ob.get("imbalance_5"),"imb10":ob.get("imbalance_10"),
            "delta5":w.get("5",{}).get("delta_pct"),"delta30":w.get("30",{}).get("delta_pct"),
            "delta60":w.get("60",{}).get("delta_pct"),"ret5":p.get("5",{}).get("return_pct"),
            "ret30":p.get("30",{}).get("return_pct"),"ret60":p.get("60",{}).get("return_pct"),
            "cvd_slope30":state.get("cvd_slope30",state.get("cvd",{}).get("slope30") if isinstance(state.get("cvd"),dict) else None),
            "spread_bps":((ask-bid)/mid*10000 if mid>0 and ask>=bid else None)}

def empirical_edges(feat,now_ts,horizons=(60,120,180),k=60,labeled_rows=None):
    """Compute several chronological KNN horizons while calculating each row distance once."""
    source=rows() if labeled_rows is None else labeled_rows
    now=float(now_ts)
    cohorts={h:[] for h in horizons}
    cutoffs={h:now-float(h) for h in horizons}
    for r in source:
        ts=float(r.get("ts",0))
        labs=r.get("labels",{})
        eligible=[]
        for h in horizons:
            if ts>=cutoffs[h]:
                continue
            lab=labs.get(str(h)) or labs.get(h)
            if isinstance(lab,dict) and finite(lab.get("move_bps")):
                eligible.append((h,float(lab["move_bps"])))
        if not eligible:
            continue
        d=distance(feat,r)
        if d>=20:
            continue
        for h,move in eligible:
            cohorts[h].append((d,move,ts))
    results={}
    for h,cohort in cohorts.items():
        cohort.sort(key=lambda x:x[0])
        cohort=cohort[:k]
        if len(cohort)<30:
            results[h]={"ready":False,"n":len(cohort),"long_bps":None,"short_bps":None}
            continue
        weights=[1/(0.05+d) for d,_,_ in cohort]
        sw=sum(weights)
        mean=sum(w*y for w,(_,y,_) in zip(weights,cohort))/sw
        var=sum(w*(y-mean)**2 for w,(_,y,_) in zip(weights,cohort))/sw
        results[h]={"ready":True,"n":len(cohort),"long_bps":mean,"short_bps":-mean,"std_bps":math.sqrt(max(0,var))}
    return results

def empirical_edge(feat,now_ts,horizon=120,k=60,labeled_rows=None):
    return empirical_edges(feat,now_ts,horizons=(horizon,),k=k,labeled_rows=labeled_rows)[horizon]

def modeled_round_trip_cost(cfg, spread_bps=0.0):
    """Conservative all-in round-trip friction; cost_floor_bps is a floor, not additive."""
    venue=cfg.get("venue",{}) if isinstance(cfg.get("venue",{}),dict) else {}
    fees=float(venue.get("effective_maker_bps",2.36))+float(venue.get("effective_taker_bps",5.90))
    friction=max(0.0,float(spread_bps))+float(cfg.get("taker_slippage_bps",1.0))+float(cfg.get("maker_adverse_selection_bps",1.5))
    return max(float(cfg.get("cost_floor_bps",0.0)),fees+friction)

def news_state(now):
    try:
        n=json.loads(NEWS.read_text()); age=float(now)-float(n.get("timestamp",0))
        if age>300:return {"usable":False,"direction":"NONE","age":age,"reason":"NEWS_STALE"}
        if not n.get("signal"):return {"usable":False,"direction":"NONE","age":age,"reason":"NEWS_NO_SIGNAL"}
        return {"usable":True,"direction":n.get("direction","NONE"),"age":age,"reason":"NEWS_CONFIRMED"}
    except:return {"usable":False,"direction":"NONE","age":None,"reason":"NEWS_UNAVAILABLE"}

def ensemble(state,candles=None,qwen=None,now_ts=None,config=None):
    now=float(now_ts or time.time()); cfg=config or json.loads(COST.read_text())
    mtf=json.loads(MTF.read_text()) if MTF.exists() else {}; candles=candles or {"timeframes":mtf.get("timeframes",{})}; v5=v5_evaluate(state,candles=candles,qwen=qwen,now_ts=now,config=cfg)
    feat=current_features(state); lab_rows=rows()
    edges=empirical_edges(feat,now,horizons=(60,120,180),labeled_rows=lab_rows)
    e60,e120,e180=edges[60],edges[120],edges[180]
    candidates=[e for e in (e60,e120,e180) if e["ready"]]
    action=v5["action"]; evidence=["V5_MICROSTRUCTURE"]
    if not candidates: return {"action":"ABSTAIN","score":0.0,"score_is_probability":False,"reason":"CALIBRATION_NOT_READY","v5":v5,"empirical":{},"paper_only":True,"real_orders":False}
    if action not in ("LONG","SHORT"): return {"action":"ABSTAIN","score":v5["score"],"score_is_probability":False,"reason":"V5_ABSTAIN","v5":v5,"empirical":{"60":e60,"120":e120,"180":e180},"paper_only":True,"real_orders":False}
    vals=[(x["long_bps"] if action=="LONG" else x["short_bps"]) for x in candidates]
    edge=sum(vals)/len(vals)
    spread=float(v5.get("spread_bps") or 0)
    modeled_cost=modeled_round_trip_cost(cfg,spread)
    net_edge=edge-modeled_cost
    news=news_state(now)
    if news["usable"] and news["direction"] not in ("NONE",action):
        return {"action":"ABSTAIN","score":v5["score"],"score_is_probability":False,"reason":"NEWS_CONFLICT","v5":v5,"empirical":{"60":e60,"120":e120,"180":e180},"net_edge_bps":net_edge,"news":news,"paper_only":True,"real_orders":False}
    if net_edge<float(cfg.get("min_net_edge_bps",1)) or abs(edge)<float(cfg.get("min_empirical_edge_bps",6)):
        return {"action":"ABSTAIN","score":v5["score"],"score_is_probability":False,"reason":"INSUFFICIENT_NET_EDGE","v5":v5,"empirical":{"60":e60,"120":e120,"180":e180},"gross_edge_bps":edge,"net_edge_bps":net_edge,"news":news,"paper_only":True,"real_orders":False}
    score=net_edge/max(1,float(sum(x.get("std_bps",1) for x in candidates)/len(candidates)))
    return {"action":action,"score":score,"score_is_probability":False,"reason":"CALIBRATED_EDGE_CONFIRMED",
            "gross_edge_bps":edge,"net_edge_bps":net_edge,"uncertainty_bps":sum(x.get("std_bps",0) for x in candidates)/len(candidates),
            "v5":v5,"empirical":{"60":e60,"120":e120,"180":e180},"news":news,
            "evidence":evidence+["EMPIRICAL_KNN_FORWARD_EDGE","COST_NETTED","NEWS_GATED"],"paper_only":True,"real_orders":False}
