"""Institutional absorption validation analytics.

Consumes only recorded paper EXIT events. Missing fields remain missing; no
historical microstructure or regime labels are synthesized.
"""
import json, math, time
from pathlib import Path
from statistics import mean, median

ROOT=Path(__file__).resolve().parents[1]
EVENTS=ROOT/"data/processed/institutional_absorption_monitor_v2.jsonl"
OUT=ROOT/"data/processed/institutional_absorption_validation_v2.json"

GATE={"minimum_labeled_trades":100,"minimum_active_accuracy":0.55,
      "minimum_avg_net_bps":0.0,"minimum_profit_factor":1.2,
      "positive_walk_forward_required":True,"conservative_cost_model":True}

def load():
    rows=[]
    if not EVENTS.exists(): return rows
    for line in EVENTS.read_text(errors="ignore").splitlines():
        try:
            x=json.loads(line)
            if x.get("event")=="EXIT": rows.append(x)
        except Exception: pass
    return sorted(rows,key=lambda x:int(x.get("ts",0)))

def stats(rows):
    n=len(rows)
    pnl=[float(x.get("pnl",0)) for x in rows]
    rs=[float(x.get("net_r",0)) for x in rows]
    wins=[x for x in rows if float(x.get("pnl",0))>0]
    losses=[x for x in rows if float(x.get("pnl",0))<=0]
    gw=sum(float(x.get("pnl",0)) for x in wins)
    gl=abs(sum(float(x.get("pnl",0)) for x in losses))
    eq=peak=dd=0.0
    for x in rows:
        eq+=float(x.get("pnl",0)); peak=max(peak,eq); dd=min(dd,eq-peak)
    holds=[float(x.get("hold_minutes",0)) for x in rows]
    return {"trades":n,"wins":len(wins),"losses":len(losses),
            "win_rate":len(wins)/n if n else 0.0,"net_pnl":sum(pnl),
            "avg_pnl":mean(pnl) if pnl else 0.0,
            "median_pnl":median(pnl) if pnl else 0.0,
            "expectancy_r":mean(rs) if rs else 0.0,
            "profit_factor":gw/gl if gl else (math.inf if gw else 0.0),
            "avg_win":mean([float(x.get("pnl",0)) for x in wins]) if wins else 0.0,
            "avg_loss":mean([float(x.get("pnl",0)) for x in losses]) if losses else 0.0,
            "avg_hold_minutes":mean(holds) if holds else 0.0,
            "max_drawdown_pnl":dd}

def grouped(rows,key):
    out={}
    for x in rows:
        k=key(x)
        if k is not None: out.setdefault(str(k),[]).append(x)
    return {k:stats(v) for k,v in out.items()}

def walk_forward(rows):
    n=len(rows)
    if n<20:
        return {"status":"INSUFFICIENT_SAMPLE","folds":[]}
    folds=[]
    chunk=max(10,n//4)
    for i in range(3):
        train_end=min(n,(i+1)*chunk)
        test_end=min(n,train_end+chunk)
        if test_end<=train_end: continue
        train=rows[:train_end]; test=rows[train_end:test_end]
        folds.append({"fold":i+1,"train":stats(train),"test":stats(test)})
    positive=sum(1 for f in folds if f["test"]["net_pnl"]>0)
    return {"status":"READY" if len(folds)>=3 else "PARTIAL",
            "folds":folds,"positive_test_folds":positive,
            "positive_test_fold_ratio":positive/len(folds) if folds else 0.0}

def confidence_bucket(x):
    c=float(x.get("confidence",0))
    return "low_<0.4" if c<0.4 else ("mid_0.4_0.7" if c<0.7 else "high_>=0.7")

def hour_bucket(x):
    ts=int(x.get("ts",0))
    return time.strftime("%H",time.localtime(ts)) if ts else None

def validate(rows, overall, wf):
    reasons=[]
    if len(rows)<GATE["minimum_labeled_trades"]: reasons.append("TRADE_SAMPLE_BELOW_100")
    if overall["win_rate"]<GATE["minimum_active_accuracy"]: reasons.append("WIN_RATE_BELOW_55_PCT")
    if overall["avg_pnl"]<GATE["minimum_avg_net_bps"]: reasons.append("NET_RESULT_BELOW_ZERO")
    if overall["profit_factor"]<GATE["minimum_profit_factor"]: reasons.append("PROFIT_FACTOR_BELOW_1.2")
    if wf.get("status")!="READY": reasons.append("WALK_FORWARD_NOT_READY")
    elif wf.get("positive_test_fold_ratio",0)<0.5: reasons.append("WALK_FORWARD_NOT_POSITIVE")
    return {"eligible_for_promotion":False,
            "gate_reasons":reasons or ["MANUAL_APPROVAL_AND_REAL_ORDER_SWITCH_REQUIRED"],
            "policy":"BLOCKED_UNTIL_VALIDATED"}

def main():
    rows=load()
    overall=stats(rows)
    wf=walk_forward(rows)
    result={"updated_at":int(time.time()),"paper_only":True,"real_orders":False,
            "sample_status":"INSUFFICIENT_SAMPLE" if len(rows)<100 else "VALIDATION_SAMPLE_REACHED",
            "overall":overall,
            "by_direction":grouped(rows,lambda x:x.get("action")),
            "by_regime":grouped(rows,lambda x:x.get("regime")),
            "by_exit_reason":grouped(rows,lambda x:x.get("reason")),
            "by_hour_local":grouped(rows,hour_bucket),
            "by_confidence":grouped(rows,confidence_bucket),
            "walk_forward":wf,
            "validation":validate(rows,overall,wf),
            "promotion_gate":GATE,
            "data_quality":{"recorded_exit_events":len(rows),
                            "missing_net_r":sum("net_r" not in x for x in rows),
                            "missing_confidence":sum("confidence" not in x for x in rows),
                            "missing_signal_reason":sum("signal_reason" not in x for x in rows)}}
    OUT.write_text(json.dumps(result,indent=2,allow_nan=False))
    print(json.dumps(result,indent=2,allow_nan=False))
    return result

if __name__=="__main__": main()
