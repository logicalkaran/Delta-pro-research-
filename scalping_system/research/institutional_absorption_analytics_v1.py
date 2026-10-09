import json, math, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
EVENTS=ROOT/"data/processed/institutional_absorption_monitor_v2.jsonl"
OUT=ROOT/"data/processed/institutional_absorption_analytics_v1.json"

def metrics(rows):
    n=len(rows); pnl=[float(x.get("pnl",0)) for x in rows]; r=[float(x.get("net_r",0)) for x in rows]
    w=[x for x in rows if float(x.get("pnl",0))>0]; l=[x for x in rows if float(x.get("pnl",0))<=0]
    gw=sum(float(x.get("pnl",0)) for x in w); gl=abs(sum(float(x.get("pnl",0)) for x in l))
    return {"trades":n,"wins":len(w),"losses":len(l),"win_rate":len(w)/n if n else 0,
            "net_pnl":sum(pnl),"avg_pnl":sum(pnl)/n if n else 0,
            "expectancy_r":sum(r)/n if n else 0,
            "profit_factor":gw/gl if gl else (math.inf if gw else 0),
            "avg_hold_minutes":sum(float(x.get("hold_minutes",0)) for x in rows)/n if n else 0}

def main():
    rows=[]
    if EVENTS.exists():
        for line in EVENTS.read_text(errors="ignore").splitlines():
            try:
                x=json.loads(line)
                if x.get("event")=="EXIT": rows.append(x)
            except Exception: pass
    overall=metrics(rows)
    by_action={}
    for a in ("LONG","SHORT"):
        by_action[a]=metrics([x for x in rows if x.get("action")==a])
    eq=peak=0.0; dd=0.0
    for x in rows:
        eq+=float(x.get("pnl",0)); peak=max(peak,eq); dd=min(dd,eq-peak)
    result={"updated_at":int(time.time()),"paper_only":True,"real_orders":False,
            "sample_status":"INSUFFICIENT_SAMPLE" if len(rows)<100 else "SAMPLE_THRESHOLD_REACHED",
            "overall":overall,"max_drawdown_pnl":dd,"by_action":by_action,
            "exit_reasons":{k:sum(1 for x in rows if x.get("reason")==k) for k in ("TARGET","STOP","TIMEOUT")},
            "promotion_gate":{"minimum_labeled_trades":100,"minimum_active_accuracy":0.55,
                              "minimum_avg_net_bps":0.0,"minimum_profit_factor":1.2,
                              "positive_walk_forward_required":True}}
    OUT.write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
if __name__=="__main__": main()
