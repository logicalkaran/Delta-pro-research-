"""Live microstructure edge tournament. Research-only; no execution authority."""
import json, math, statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
LAB=ROOT/'data/processed/live_microstructure_labeled_v1.jsonl'
OUT=ROOT/'data/processed/live_edge_tournament_v1.json'
FEATURES=['imb5','imb10','delta5','delta30','delta60','ret5','ret30','ret60','cvd_slope30']
REGIMES=['ALL','BUY_PRESSURE','BUYER_CONFIRMATION','BUYER_ABSORPTION','SELL_PRESSURE','SELLER_CONFIRMATION','SELLER_ABSORPTION']
HORIZONS=[60,120,180,300]
COST_BPS=8.26+1.0+1.5

def load():
 rows=[]
 for line in LAB.read_text().splitlines() if LAB.exists() else []:
  try:
   r=json.loads(line)
   if isinstance(r,dict) and isinstance(r.get('labels'),dict): rows.append(r)
  except: pass
 return rows

def num(r,k):
 try:
  x=float(r.get(k)); return x if math.isfinite(x) else None
 except: return None

def report(rows):
 results=[]
 for h in HORIZONS:
  base=[]
  for r in rows:
   lab=r.get('labels',{}).get(str(h),{})
   y=num(lab,'move_bps') if isinstance(lab,dict) else None
   if y is None: continue
   base.append((r,y))
  for regime in REGIMES:
   cohort=[(r,y) for r,y in base if regime=='ALL' or r.get('regime')==regime]
   if len(cohort)<50: continue
   for feature in FEATURES:
    vals=[(num(r,feature),y) for r,y in cohort]
    vals=[x for x in vals if x[0] is not None]
    if len(vals)<50: continue
    vals.sort(key=lambda z:z[0])
    q=max(10,len(vals)//5)
    for side,subset in [('LONG',vals[-q:]),('SHORT',vals[:q])]:
     gross=statistics.fmean(y if side=='LONG' else -y for _,y in subset)
     net=gross-COST_BPS
     half=len(subset)//2
     a=[y if side=='LONG' else -y for _,y in subset[:half]]
     b=[y if side=='LONG' else -y for _,y in subset[half:]]
     results.append({'horizon_s':h,'regime':regime,'feature':feature,'side':side,'n':len(subset),'gross_avg_bps':gross,'net_avg_bps':net,'positive_rate':sum(v>0 for v in [y if side=='LONG' else -y for _,y in subset])/len(subset),'first_half_net_bps':statistics.fmean(a)-COST_BPS if a else 0,'second_half_net_bps':statistics.fmean(b)-COST_BPS if b else 0})
 results.sort(key=lambda x:(x['net_avg_bps'],x['n']),reverse=True)
 return results

rows=load(); res=report(rows)
positive=[x for x in res if x['n']>=50 and x['net_avg_bps']>0 and x['first_half_net_bps']>0 and x['second_half_net_bps']>0]
out={'schema':'live_edge_tournament_v1','research_only':True,'real_orders':False,'rows_loaded':len(rows),'cost_floor_bps':COST_BPS,'horizons':HORIZONS,'results':res[:100],'positive_stable_candidates':positive[:25]}
OUT.write_text(json.dumps(out,indent=2)); print(json.dumps({'rows_loaded':len(rows),'candidates':len(res),'positive_stable':len(positive),'top':res[:10]},indent=2))
