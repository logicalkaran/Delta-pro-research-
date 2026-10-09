"""Evaluate forward tournament outcomes; no execution authority."""
from pathlib import Path
import json,time,math
ROOT=Path(__file__).resolve().parents[1]; SRC=ROOT/"data/processed/strategy_forward_tournament_v1.jsonl"; OUT=ROOT/"data/processed/forward_tournament_evaluation_v1.json"
def main():
 rows=[]
 if SRC.exists():
  for line in SRC.read_text().splitlines():
   try: rows.append(json.loads(line))
   except: pass
 groups={}
 for r in rows:
  k=(r.get("strategy"),r.get("horizon"),r.get("regime")); g=groups.setdefault(k,[]); g.append(float(r.get("net_return_pct",0)))
 reports=[]
 for k,v in groups.items():
  n=len(v); wins=sum(x>0 for x in v); loss=sum(x<0 for x in v); pf=sum(x for x in v if x>0)/abs(sum(x for x in v if x<0)) if loss else None
  reports.append({"strategy":k[0],"horizon":k[1],"regime":k[2],"samples":n,"win_rate":wins/n if n else None,"avg_net_return_pct":sum(v)/n if n else None,"profit_factor":pf,"eligible":n>=30 and sum(v)/n>0 and (pf or 0)>=1.2})
 eligible=[x for x in reports if x["eligible"]]
 eligible.sort(key=lambda x:(x["avg_net_return_pct"],x["profit_factor"] or 0),reverse=True)
 out={"updated_at":time.time(),"total_outcomes":len(rows),"groups":reports,"eligible_candidates":eligible[:10],"selection_rule":">=30 forward outcomes, positive average net return, PF>=1.2","paper_only":True,"real_orders":False,"promotion_allowed":False}
 OUT.write_text(json.dumps(out,indent=2)); print(json.dumps({"total_outcomes":len(rows),"eligible":len(eligible),"top":eligible[:3]},indent=2))
if __name__=="__main__":main()
