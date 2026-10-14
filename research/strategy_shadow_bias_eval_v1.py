"""Evaluate bias-conflict shadow outcomes; diagnostic only."""
from pathlib import Path
import json,collections,time
ROOT=Path(__file__).resolve().parents[1]
LOG=ROOT/"data/processed/strategy_shadow_bias_v1.jsonl"; OUT=ROOT/"data/processed/strategy_shadow_bias_eval_v1.json"
def main():
 rows=[]
 if LOG.exists():
  for line in LOG.read_text().splitlines():
   try: rows.append(json.loads(line))
   except: pass
 ex=[x for x in rows if x.get("event")=="SHADOW_EXIT"]
 wins=[x for x in ex if float(x.get("net_pnl_usd",0))>0]; losses=[x for x in ex if float(x.get("net_pnl_usd",0))<=0]
 pos=2.0; peak=2.0; mdd=0
 by=collections.defaultdict(lambda:{"trades":0,"wins":0,"net":0.0})
 for x in ex:
  pnl=float(x.get("net_pnl_usd",0)); pos+=pnl; peak=max(peak,pos); mdd=max(mdd,1-pos/peak if peak else 1)
  b=by[x.get("strategy","UNKNOWN")]; b["trades"]+=1; b["wins"]+=int(pnl>0); b["net"]+=pnl
 grosswin=sum(float(x.get("net_pnl_usd",0)) for x in wins); grossloss=abs(sum(float(x.get("net_pnl_usd",0)) for x in losses))
 r={"updated_at":int(time.time()),"trades":len(ex),"wins":len(wins),"losses":len(losses),
 "win_rate":len(wins)/len(ex) if ex else None,"net_pnl_usd":pos-2,"profit_factor":grosswin/grossloss if grossloss else None,
 "max_drawdown":mdd,"by_strategy":dict(by),"status":"INSUFFICIENT_SAMPLE" if len(ex)<30 else "SHADOW_SAMPLE_READY",
 "promotion_allowed":False,"paper_only":True}
 OUT.write_text(json.dumps(r,indent=2)); print(json.dumps(r,indent=2))
if __name__=="__main__": main()
