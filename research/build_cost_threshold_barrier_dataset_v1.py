"""Build first-touch +20/-10 bps directional labels from the microstructure tape.
Labels are for training/research only; the script does not fit or deploy a model.
"""
from pathlib import Path
import json
from bisect import bisect_right
from research.cost_threshold_maker_shadow_v1 import BarrierConfig, first_touch_label
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'data/processed/live_microstructure_features_v1.jsonl'
OUT=ROOT/'data/processed/cost_threshold_barrier_labels_v1.jsonl'
CFG=BarrierConfig(target_bps=20.0,stop_bps=10.0,horizon_seconds=300.0,min_net_bps=5.0,assumed_round_trip_cost_bps=15.8)

def main():
 rows=[]
 if SRC.exists():
  for line in SRC.open(encoding='utf-8'):
   try:
    r=json.loads(line); ts=float(r.get('ts',0)); mid=float(r.get('mid',0))
    if ts>0 and mid>0: rows.append(r)
   except (ValueError,TypeError): pass
 rows.sort(key=lambda r:float(r['ts']))
 out=[]; complete=0
 times=[float(r['ts']) for r in rows]
 # Reject horizons crossing capture gaps; these would join unrelated sessions and create false labels.
 gap_prefix=[0]
 for j in range(1,len(times)):
  gap_prefix.append(gap_prefix[-1] + (1 if times[j]-times[j-1] > 3.0 else 0))
 for i,r in enumerate(rows):
  ts=float(r['ts']); mid=float(r['mid'])
  end=bisect_right(times,ts+CFG.horizon_seconds)
  if end<=i+1 or times[end-1]-ts < CFG.horizon_seconds-CFG.coverage_tolerance_seconds: continue
  if gap_prefix[end-1]-gap_prefix[i] > 0: continue
  path=rows[i+1:end]
  complete+=1
  for side,name in ((1,'LONG'),(-1,'SHORT')):
   label=first_touch_label(mid,path,side,CFG,entry_ts=ts)
   out.append({'ts':ts,'mid':mid,'side':name,'label':label['label'],'class':label['class'],
    'touch_seconds':label['touch_seconds'],'terminal_move_bps':label['move_bps'],
    'target_bps':CFG.target_bps,'stop_bps':CFG.stop_bps,'horizon_seconds':CFG.horizon_seconds,
    'features':{k:r.get(k) for k in ('spread_bps','imb5','imb10','microprice_shift','microprice_direction','signed_flow_1s','delta5','delta30','delta60','ret5','ret30','ret60','cvd_slope30','regime','fresh')}})
 OUT.parent.mkdir(parents=True,exist_ok=True)
 OUT.write_text(''.join(json.dumps(x,separators=(',',':'),allow_nan=False)+'\n' for x in out),encoding='utf-8')
 from collections import Counter
 c=Counter(x['class'] for x in out)
 print(json.dumps({'status':'RESEARCH_LABELS_ONLY','source':str(SRC.relative_to(ROOT)),'output':str(OUT.relative_to(ROOT)),
  'source_rows':len(rows),'complete_300s_entry_rows':complete,'labeled_directional_rows':len(out),
  'class_counts':dict(c),'target_bps':CFG.target_bps,'stop_bps':CFG.stop_bps,'horizon_seconds':CFG.horizon_seconds,
  'note':'No model trained. Rows overlap and are not independent. Purged chronological validation required. No live orders.'},indent=2))
if __name__=='__main__': main()
