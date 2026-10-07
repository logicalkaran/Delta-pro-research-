"""Professional Paper Strategy V1.
One-hour live paper evaluation. No exchange orders.
Uses current microstructure + V4 score + cross-venue state when available.
"""
import json,time,os,statistics
from strategy.market_intelligence_v4 import features,score
STATE="data/live_microstructure_state.json"
CROSS="data/processed/cross_venue_btc_v43.jsonl"
LOG="data/processed/professional_paper_v1.jsonl"
SUMMARY="data/processed/professional_paper_v1_summary.json"
HOLD=30.0; COST_BPS=11.8; STOP_BPS=8.0; TARGET_BPS=16.0

def read_json(p):
    try:
        with open(p) as f:return json.load(f)
    except:return None
def cross():
    try:
        with open(CROSS) as f:
            lines=f.readlines()
            return json.loads(lines[-1]) if lines else None
    except:return None
def price(s):
    return float(s.get("order_book",{}).get("mid_price",0))
def signal(s,c):
    f=features(s); sc=score(f); action=sc["action"]
    cross_state=(c or {}).get("edge_v42",{}).get("state","NO_DATA")
    # Require meaningful multi-factor alignment; cross venue is confirmation,
    # not an unvalidated directional predictor.
    if action=="NO_TRADE" or sc["score"]<6:
        return "NO_TRADE",sc["score"],"V4_THRESHOLD"
    if cross_state=="DIVERGENCE":
        return "NO_TRADE",sc["score"],"CROSS_DIVERGENCE_BLOCK"
    return action,sc["score"],"PROFESSIONAL_ALIGNMENT"

def run(seconds=3600):
    os.makedirs(os.path.dirname(LOG),exist_ok=True)
    start=time.time(); pos=None; trades=[]; candidates=0; rejects={}
    while time.time()-start<seconds:
        s=read_json(STATE); c=cross()
        if not s:
            time.sleep(.5); continue
        px=price(s)
        if px<=0: time.sleep(.5); continue
        action,sc,reason=signal(s,c)
        candidates += action!="NO_TRADE"
        if action=="NO_TRADE":
            rejects[reason]=rejects.get(reason,0)+1
        if pos is None and action in ("LONG","SHORT"):
            pos={"side":action,"entry":px,"time":time.time(),"score":sc}
        elif pos is not None:
            age=time.time()-pos["time"]; move=(px/pos["entry"]-1)*10000
            signed=move if pos["side"]=="LONG" else -move
            exit_reason=None
            if signed>=TARGET_BPS: exit_reason="TARGET"
            elif signed<=-STOP_BPS: exit_reason="STOP"
            elif age>=HOLD: exit_reason="TIME"
            if exit_reason:
                net=signed-COST_BPS
                trades.append({"side":pos["side"],"entry":pos["entry"],"exit":px,
                    "gross_bps":signed,"net_bps":net,"hold_s":age,
                    "score":pos["score"],"exit_reason":exit_reason,
                    "ts":time.time()})
                pos=None
        with open(LOG,"a") as f:
            f.write(json.dumps({"ts":time.time(),"price":px,"action":action,
                "score":sc,"reason":reason,"position":pos,
                "cross_state":(c or {}).get("edge_v42",{}).get("state","NO_DATA")},separators=(",",":"))+"\n")
        time.sleep(.5)
    if pos is not None:
        s=read_json(STATE); px=price(s) if s else pos["entry"]
        move=(px/pos["entry"]-1)*10000
        signed=move if pos["side"]=="LONG" else -move
        trades.append({"side":pos["side"],"entry":pos["entry"],"exit":px,
            "gross_bps":signed,"net_bps":signed-COST_BPS,"hold_s":time.time()-pos["time"],
            "score":pos["score"],"exit_reason":"SESSION_END","ts":time.time()})
    vals=[t["net_bps"] for t in trades]
    wins=[v for v in vals if v>0]; losses=[-v for v in vals if v<0]
    summary={"duration_s":time.time()-start,"trades":len(trades),
      "wins":len(wins),"losses":len(losses),
      "win_rate":len(wins)/len(vals) if vals else 0,
      "avg_net_bps":sum(vals)/len(vals) if vals else 0,
      "total_net_bps":sum(vals),
      "profit_factor":sum(wins)/sum(losses) if losses else None,
      "candidates":candidates,"rejections":rejects,
      "cost_model_bps_per_roundtrip":COST_BPS,
      "hold_s":HOLD,"stop_bps":STOP_BPS,"target_bps":TARGET_BPS,
      "status":"PAPER_ONLY","real_orders":False,"trades_detail":trades}
    json.dump(summary,open(SUMMARY,"w"),indent=2)
    print(json.dumps(summary,indent=2),flush=True)
if __name__=="__main__":run()
