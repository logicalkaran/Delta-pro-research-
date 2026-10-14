"""Score completed 1-5m forecasts from the immutable forecast journal."""
from pathlib import Path
import json,time
ROOT=Path(__file__).resolve().parents[1]; LOG=ROOT/"data/processed/short_horizon_forecasts_v1.jsonl"; C=ROOT/"data/live_candles.json"; OUT=ROOT/"data/processed/short_horizon_calibration_v1.json"
def read(p):
 try:return json.loads(p.read_text())
 except:return None
def main():
 rows=[]; candles=read(C) or []
 if LOG.exists():
  for line in LOG.read_text().splitlines():
   try: rows.append(json.loads(line))
   except: pass
 closes=[(float(x.get("timestamp",0)),float(x.get("close",0))) for x in candles if float(x.get("close",0) or 0)>0]
 done=0; correct={i:0 for i in range(1,6)}; total={i:0 for i in range(1,6)}; mae={i:0.0 for i in range(1,6)}
 for r in rows:
  t=float(r["issued_at"]); p=float(r["price"])
  for f in r.get("forecasts",[]):
   m=int(f["minutes"]); future=[x for x in closes if x[0]>=t+m*60]
   if not future: continue
   fp=future[0][1]; actual=(fp/p-1)*100; prob=float(f["probability_up"]); direction=f["direction"]
   actual_dir="UP" if actual>0 else ("DOWN" if actual<0 else "NEUTRAL")
   total[m]+=1; correct[m]+=int(direction==actual_dir)
   mae[m]+=abs(actual-float(f["expected_return_pct"])); done+=1
 out={"updated_at":int(time.time()),"scored_points":done,
 "horizons":{str(m):{"samples":total[m],"directional_accuracy":correct[m]/total[m] if total[m] else None,
 "mean_abs_return_error_pct":mae[m]/total[m] if total[m] else None} for m in range(1,6)},
 "status":"CALIBRATION_RUNNING","paper_only":True,"promotion_allowed":False}
 OUT.write_text(json.dumps(out,indent=2)); print(json.dumps(out,indent=2))
if __name__=="__main__": main()
