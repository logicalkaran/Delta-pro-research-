"""Paper-only telemetry leaderboard for Composite Edge V2."""
from pathlib import Path
import json,time
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"data/processed/strategy_forward_tournament_v1.jsonl"
OUT=ROOT/"data/processed/composite_v2_leaderboard.json"

def main():
 rows=[]
 if SRC.exists():
  for line in SRC.read_text().splitlines():
   try:
    r=json.loads(line)
    if r.get("strategy")=="COMPOSITE_EDGE_V2" and r.get("expected_edge_bps") is not None and "net_return_pct" in r: rows.append(r)
   except: pass
 groups={}
 for r in rows:
  edge=float(r.get("expected_edge_bps",0)); band="15-20" if edge<20 else "20-30" if edge<30 else "30+"
  key=(band,int(r.get("horizon",0)))
  groups.setdefault(key,[]).append(r)
 reports=[]
 for (band,h),rs in sorted(groups.items()):
  vals=[float(x.get("net_return_pct",0)) for x in rs]
  wins=sum(v>0 for v in vals); avg=sum(vals)/len(vals) if vals else 0
  gross_w=sum(v for v in vals if v>0); gross_l=abs(sum(v for v in vals if v<0)); pf=gross_w/gross_l if gross_l else None
  reports.append({"edge_band_bps":band,"horizon":h,"samples":len(vals),"win_rate":wins/len(vals) if vals else None,"avg_net_return_pct":avg,"profit_factor":pf})
 out={"updated_at":time.time(),"samples":len(rows),"groups":reports,"paper_only":True,"promotion_allowed":False,"note":"Telemetry only; no threshold relaxation or live execution."}
 OUT.write_text(json.dumps(out,indent=2)); print(json.dumps(out,indent=2))
if __name__=="__main__":main()
