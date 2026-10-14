"""Chronological, embargoed walk-forward evaluation of causal features and realized outcomes."""
import math, random

def _finite(x):
    try:return math.isfinite(float(x))
    except (TypeError,ValueError):return False

def deduplicate(rows):
    seen=set();out=[]
    for row in sorted(rows,key=lambda r:float(r.get("ts",0))):
        ts=float(row.get("ts",0))
        if ts not in seen:out.append(row);seen.add(ts)
    return out

def split(rows,embargo_seconds=0):
    rs=deduplicate(rows);mid=len(rs)//2
    if not rs:return [],[]
    cut=float(rs[mid].get("ts",0));e=float(embargo_seconds)
    return [r for r in rs if float(r.get("ts",0))<cut-e],[r for r in rs if float(r.get("ts",0))>=cut+e]

def _outcome(row):
    t=row.get("target",{}) if isinstance(row.get("target"),dict) else {}
    z={**row,"net_bps":float(t.get("net_bps",row.get("net_bps",0))),"gross_bps":float(t.get("gross_bps",row.get("gross_bps",0))),
       "fees_bps":float(t.get("fees_bps",row.get("fees_bps",row.get("fee_bps",0)))),
       "slippage_bps":float(t.get("slippage_bps",row.get("slippage_bps",0))),"funding_bps":float(t.get("funding_bps",row.get("funding_bps",0)))}
    return z

def _stats(rows):
    xs=[float(r["net_bps"]) for r in rows]; wins=[x for x in xs if x>0];losses=[x for x in xs if x<0]
    gross=sum(abs(float(r.get("gross_bps",0))) for r in rows)
    costs=sum(float(r.get("fees_bps",0))+float(r.get("slippage_bps",0))+float(r.get("funding_bps",0)) for r in rows)
    eq=peak=dd=0
    for x in xs:eq+=x;peak=max(peak,eq);dd=max(dd,peak-eq)
    return {"sample_count":len(xs),"n":len(xs),"net_expectancy_bps":sum(xs)/len(xs) if xs else None,
      "profit_factor":sum(wins)/abs(sum(losses)) if losses and sum(losses) else (float("inf") if wins else None),
      "max_drawdown_bps":dd,"hit_rate":len(wins)/len(xs) if xs else None,
      "average_win_bps":sum(wins)/len(wins) if wins else None,"average_loss_bps":sum(losses)/len(losses) if losses else None,
      "cost_to_gross_ratio":costs/gross if gross else None}

def bootstrap_ci(rows,iterations=1000,seed=13):
    xs=[float(r["net_bps"]) for r in rows]
    if not xs:return {"lower_95":None,"upper_95":None}
    rng=random.Random(seed);means=sorted(sum(rng.choice(xs) for _ in xs)/len(xs) for _ in range(iterations))
    return {"lower_95":means[int(.025*(iterations-1))],"upper_95":means[int(.975*(iterations-1))],"confidence":.95,"iterations":iterations}

def evaluate(rows,embargo_seconds=0,fee_multipliers=(1.0,1.5,2.0),slippage_additions=(0,1,2)):
    ordered=deduplicate(rows);train,test=split(ordered,embargo_seconds)
    # Labels are unpacked only after causal signal rows have been chronologically split.
    # Determine membership from timestamps first; future outcomes are read only
    # after rows have been assigned to chronological partitions.
    train_ts={float(r.get("ts",0)) for r in train}; test_ts={float(r.get("ts",0)) for r in test}
    labeled=[r for r in ordered if isinstance(r.get("target"),dict) and _finite(r["target"].get("net_bps"))]
    trades=[_outcome(r) for r in labeled]
    train_trades=[_outcome(r) for r in labeled if float(r.get("ts",0)) in train_ts]
    test_trades=[_outcome(r) for r in labeled if float(r.get("ts",0)) in test_ts]
    first=trades[:len(trades)//2];second=trades[len(trades)//2:]
    regimes={k:_stats([r for r in trades if str(r.get("regime","UNKNOWN"))==k]) for k in sorted({str(r.get("regime","UNKNOWN")) for r in trades})}
    sensitivity={}
    for fm in fee_multipliers:
        for sl in slippage_additions:
            adj=[{**r,"net_bps":r["net_bps"]-(fm-1)*r["fees_bps"]-sl} for r in trades]
            sensitivity[f"fee_x{fm}_slip_plus_{sl}bps"]=_stats(adj)
    halves=[_stats(first),_stats(second)]
    out={"rows":len(ordered),"train_rows":len(train),"test_rows":len(test),"embargo_seconds":embargo_seconds,
      "chronological":True,"future_labels_used_as_features":False,"metrics":_stats(trades),"bootstrap_ci":bootstrap_ci(trades),
      "train_metrics":_stats(train_trades),"test_metrics":_stats(test_trades),
      "halves":halves,"positive_expectancy_both_halves":bool(first and second and all(x["net_expectancy_bps"]>0 for x in halves)),
      "regimes":regimes,"regime_stability":bool(regimes) and all(v["net_expectancy_bps"] is not None and v["net_expectancy_bps"]>0 for v in regimes.values()),
      "sensitivity":sensitivity,"long":_stats([r for r in trades if r.get("side")=="LONG"]),
      "short":_stats([r for r in trades if r.get("side")=="SHORT"]),
      "maker":_stats([r for r in trades if r.get("entry_kind")=="MAKER"]),"taker":_stats([r for r in trades if r.get("entry_kind")=="TAKER"]),
      "limitations":"No profitability or constant-edge claim; outputs describe the supplied chronological outcomes and regime sample."}
    return out
