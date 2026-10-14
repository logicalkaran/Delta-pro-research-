"""Forward tournament evaluator v2: overlap control + stability checks. Research only."""
from pathlib import Path
import json,time
ROOT=Path(__file__).resolve().parents[1]; SRC=ROOT/"data/processed/strategy_forward_tournament_v1.jsonl"; OUT=ROOT/"data/processed/forward_tournament_evaluation_v2.json"
MIN=30; GAP=60
def main():
 rows=[]
 if SRC.exists():
  for line in SRC.read_text().splitlines():
   try: rows.append(json.loads(line))
   except: pass
 groups={}
 for r in rows: groups.setdefault((r.get("strategy"),int(r.get("horizon",0)),r.get("regime")),[]).append(r)
 reports=[]
 for k,rs in groups.items():
  rs.sort(key=lambda x:x.get("issued_at",0)); selected=[]; last=-1e18
  for r in rs:
   t=float(r.get("issued_at",0))
   if t-last>=GAP: selected.append(r); last=t
  vals=[float(r.get("net_return_pct",0)) for r in selected]; n=len(vals); wins=sum(v>0 for v in vals)
  mid=n//2; a=vals[:mid]; b=vals[mid:]
  avg=sum(vals)/n if n else 0; p=sum(v for v in vals if v>0)/abs(sum(v for v in vals if v<0)) if any(v<0 for v in vals) else None
  aavg=sum(a)/len(a) if a else None; bavg=sum(b)/len(b) if b else None
  stable=bool(n>=MIN and avg>0 and aavg is not None and bavg is not None and aavg>0 and bavg>0 and (p or 0)>=1.2)
  reports.append({"strategy":k[0],"horizon":k[1],"regime":k[2],"raw_samples":len(rs),"independent_samples":n,"win_rate":wins/n if n else None,"avg_net_return_pct":avg,"profit_factor":p,"first_half_avg_pct":aavg,"second_half_avg_pct":bavg,"stable":stable,"eligible":stable})
 eligible=sorted([x for x in reports if x["eligible"]],key=lambda x:(x["avg_net_return_pct"],x["profit_factor"] or 0),reverse=True)
 out={"updated_at":time.time(),"total_raw_outcomes":len(rows),"groups":reports,"top_stable_candidates":eligible[:10],"rules":{"min_independent_samples":MIN,"min_signal_gap_seconds":GAP,"min_profit_factor":1.2,"positive_both_halves":True},"paper_only":True,"real_orders":False,"promotion_allowed":False}
 OUT.write_text(json.dumps(out,indent=2)); print(json.dumps({"raw":len(rows),"groups":len(reports),"stable_candidates":len(eligible),"top":eligible[:3]},indent=2))
if __name__=="__main__":main()
