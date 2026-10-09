"""Fast interaction tournament. Research-only."""
import json, math, statistics
from itertools import combinations
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; LAB=ROOT/"data/processed/live_microstructure_labeled_v1.jsonl"; OUT=ROOT/"data/processed/live_interaction_tournament_v1.json"
F=["imb5","imb10","delta5","delta30","delta60","ret5","ret30","ret60","cvd_slope30"]; H=[60,120,180,300]; COST=10.76
def num(x):
 try:
  x=float(x); return x if math.isfinite(x) else None
 except: return None
def load():
 out=[]
 for line in LAB.read_text().splitlines() if LAB.exists() else []:
  try:
   r=json.loads(line)
   if isinstance(r,dict) and isinstance(r.get("labels"),dict): out.append(r)
  except: pass
 return out
def calc(rows):
 out=[]
 for h in H:
  base=[]
  for r in rows:
   lab=r.get("labels",{}).get(str(h),{})
   y=num(lab.get("move_bps")) if isinstance(lab,dict) else None
   if y is not None: base.append((r,y))
  for a,b in combinations(F,2):
   vals=[(num(r.get(a)),num(r.get(b)),y) for r,y in base]
   vals=[v for v in vals if v[0] is not None and v[1] is not None]
   if len(vals)<80: continue
   ma=statistics.median(v[0] for v in vals); mb=statistics.median(v[1] for v in vals)
   for side,sgn in (("LONG",1),("SHORT",-1)):
    ys=[sgn*y for x,z,y in vals if (x>=ma and z>=mb) if side=='LONG'] if side=='LONG' else [sgn*y for x,z,y in vals if (x<=ma and z<=mb)]
    if len(ys)<40: continue
    # Selection uses only contemporaneous features; never sort by future label.
    ys=ys[:]
    mid=len(ys)//2
    first=statistics.fmean(ys[:mid]); second=statistics.fmean(ys[mid:])
    gross=statistics.fmean(ys)
    out.append({"horizon_s":h,"a":a,"b":b,"side":side,"n":len(ys),"gross_avg_bps":gross,"net_avg_bps":gross-COST,"first_half_net_bps":first-COST,"second_half_net_bps":second-COST,"positive_rate":sum(y>0 for y in ys)/len(ys)})
 return sorted(out,key=lambda x:(x["net_avg_bps"],x["n"]),reverse=True)
rows=load(); res=calc(rows); stable=[x for x in res if x["n"]>=50 and x["net_avg_bps"]>0 and x["first_half_net_bps"]>0 and x["second_half_net_bps"]>0]
OUT.write_text(json.dumps({"schema":"live_interaction_tournament_v1","research_only":True,"real_orders":False,"rows_loaded":len(rows),"cost_floor_bps":COST,"tested_pairs":len(list(combinations(F,2))),"results":res[:150],"stable_positive":stable[:30]},indent=2))
print(json.dumps({"rows_loaded":len(rows),"tested_pairs":len(list(combinations(F,2))),"results":len(res),"stable_positive":len(stable),"top":res[:10]},indent=2))
