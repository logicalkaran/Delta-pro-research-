"""Paper-only scalper forecast outcome tracker.
Records forecast snapshots and scores them against later BTC price.
Never places orders and never changes production execution state.
"""
import json,os,time
ROOT=os.path.expanduser("~/btc_fisher_trader")
FORECAST_LOG=os.path.join(ROOT,"data/processed/scalper_forecasts.jsonl")
OUTCOME_LOG=os.path.join(ROOT,"data/processed/scalper_forecast_outcomes.jsonl")

def _price(state):
    try:return float(state["order_book"]["mid_price"])
    except:return 0.0

def record(state,forecast,horizon_s=30):
    p=_price(state)
    if not p:return False
    row={"ts":time.time(),"symbol":state.get("symbol","BTCUSD"),"price":p,"horizon_s":int(horizon_s),
         "direction":forecast.get("horizon_30s",{}).get("direction","UNRELIABLE"),
         "prob_up":forecast.get("prob_up"),"confidence":forecast.get("horizon_30s",{}).get("strength"),
         "regime":forecast.get("regime"),"raw_score":forecast.get("raw_score"),
         "spread_bps":forecast.get("spread_bps"),"paper_only":True}
    os.makedirs(os.path.dirname(FORECAST_LOG),exist_ok=True)
    with open(FORECAST_LOG,"a") as f:f.write(json.dumps(row,separators=(",",":"))+"\n")
    return True

def settle_once(state):
    p=_price(state)
    if not p or not os.path.exists(FORECAST_LOG):return 0
    now=time.time(); rows=[]
    with open(FORECAST_LOG) as f: rows=[json.loads(x) for x in f if x.strip()]
    done=0
    with open(OUTCOME_LOG,"a") as out:
        for r in rows:
            if r.get("settled") or now-float(r.get("ts",now))<r.get("horizon_s",30):continue
            move=(p/float(r["price"])-1)*10000
            d=r.get("direction")
            if d=="UP": correct=move>0
            elif d=="DOWN": correct=move<0
            else: correct=abs(move)<0.5
            result=dict(r);result.update({"settled":True,"settled_ts":now,"move_bps":round(move,3),"correct":bool(correct)})
            out.write(json.dumps(result,separators=(",",":"))+"\n");r["settled"]=True;done+=1
    with open(FORECAST_LOG,"w") as f:
        for r in rows:f.write(json.dumps(r,separators=(",",":"))+"\n")
    return done

def stats():
    rows=[]
    try:
        with open(OUTCOME_LOG) as f:rows=[json.loads(x) for x in f if x.strip()]
    except:return {"n":0,"accuracy":None,"avg_move_bps":None,"status":"UNVALIDATED","paper_only":True}
    n=len(rows);acc=sum(bool(r.get("correct")) for r in rows)/n if n else None
    avg=sum(float(r.get("move_bps",0)) for r in rows)/n if n else None
    return {"n":n,"accuracy":round(acc,4) if acc is not None else None,"avg_move_bps":round(avg,3) if avg is not None else None,
            "status":"RESEARCH_ONLY" if n<100 else "CALIBRATION_CANDIDATE","paper_only":True,"order_submission":False}
