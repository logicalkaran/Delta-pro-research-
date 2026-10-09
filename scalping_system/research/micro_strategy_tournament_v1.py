"""Paper-only strategy tournament for the $2 challenge.
Compares normalized outcome sequences; no live execution.
"""
from pathlib import Path
import json,time
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"data/processed/strategy_shadow_counterfactual_v1.json"
OUT=ROOT/"data/processed/micro_strategy_tournament_v1.json"
START=2.0; RISK=.10; TARGET=4.0; DD=.20; STREAK=2

def run(name,rows,mult):
    eq=START; peak=eq; wins=losses=streak=0; maxdd=0
    for x in rows:
        if x.get("outcome")=="TARGET": r=2.0*mult
        elif x.get("outcome")=="STOP": r=-1.0
        else: r=max(-1,min(2,float(x.get("net_bps",0))/50))*mult
        pnl=eq*RISK*r; eq+=pnl; peak=max(peak,eq); maxdd=max(maxdd,1-eq/peak)
        if pnl>0:wins+=1;streak=0
        else:losses+=1;streak+=1
        if eq>=TARGET or maxdd>=DD or streak>=STREAK: break
    n=wins+losses
    return {"strategy":name,"ending_equity":round(eq,6),"trades":n,"win_rate":wins/n if n else 0,
            "max_drawdown":round(maxdd,4),"target_reached":eq>=TARGET,"loss_streak":streak}

def main():
    d=json.loads(SRC.read_text()); rows=d.get("outcomes",[])
    # Variants are deliberately conservative transformations of the same observed
    # counterfactual outcomes, not claims of independent historical backtests.
    results=[run("STRICT_ABSORPTION",rows,1.0),run("HIGH_CONVICTION",rows,0.75),run("NORMALIZED_2R",rows,1.0)]
    results.sort(key=lambda x:(x["target_reached"],x["ending_equity"],-x["max_drawdown"]),reverse=True)
    out={"updated_at":int(time.time()),"sample":len(rows),"results":results,
         "selection_policy":"target_then_equity_then_drawdown","paper_only":True,"real_orders":False,
         "note":"Variants share the same shadow sample; this is diagnostic, not independent validation."}
    OUT.write_text(json.dumps(out,indent=2)); print(json.dumps(out,indent=2))
if __name__=="__main__":main()
