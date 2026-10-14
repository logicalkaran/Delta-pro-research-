"""Paper-only $2->$4 challenge analytics.
Consumes existing shadow counterfactual outcomes; never submits orders.
"""
from pathlib import Path
import json,time
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"data/processed/strategy_shadow_counterfactual_v1.json"
OUT=ROOT/"data/processed/micro_challenge_backtest_v1.json"
START=2.0; TARGET=4.0; RISK=0.10; MAX_DD=0.20; LOSS_STOP=2

def main():
    if not SRC.exists(): raise SystemExit("shadow results unavailable")
    d=json.loads(SRC.read_text())
    rows=d.get("outcomes",[])
    eq=START; peak=eq; maxdd=0; wins=losses=0; streak=0; maxstreak=0; taken=[]
    for x in rows:
        net_bps=float(x.get("net_bps",0))
        # Fixed fractional risk. Outcome is normalized by a 2R target/stop model.
        r=2.0 if x.get("outcome")=="TARGET" else (-1.0 if x.get("outcome")=="STOP" else max(-1.0,min(2.0,net_bps/50.0)))
        pnl=eq*RISK*r
        eq+=pnl; peak=max(peak,eq); dd=1-eq/peak
        maxdd=max(maxdd,dd)
        if pnl>0: wins+=1; streak=0
        else: losses+=1; streak+=1; maxstreak=max(maxstreak,streak)
        taken.append({"side":x.get("side"),"outcome":x.get("outcome"),"r":round(r,3),"pnl":round(pnl,6),"equity":round(eq,6)})
        if eq>=TARGET or dd>=MAX_DD or streak>=LOSS_STOP: break
    result={"updated_at":int(time.time()),"starting_equity":START,"ending_equity":eq,
            "target_reached":eq>=TARGET,"max_drawdown":maxdd,"trades":len(taken),
            "wins":wins,"losses":losses,"win_rate":wins/len(taken) if taken else 0,
            "max_consecutive_losses":maxstreak,"stopped_by":"TARGET" if eq>=TARGET else ("DRAWDOWN" if maxdd>=MAX_DD else ("LOSS_STREAK" if streak>=LOSS_STOP else "DATA_END")),
            "paper_only":True,"real_orders":False,"production_strategy_unchanged":True,"trades":taken}
    OUT.write_text(json.dumps(result,indent=2)); print(json.dumps({k:v for k,v in result.items() if k!="trades"},indent=2))
if __name__=="__main__": main()
