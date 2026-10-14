"""Continuous out-of-sample calibration report for the 1-5m predictor."""
from pathlib import Path
import json,time
ROOT=Path(__file__).resolve().parents[1]
J=ROOT/"data/processed/short_horizon_forecasts_v1.jsonl"; C=ROOT/"data/live_candles.json"; O=ROOT/"data/processed/short_horizon_calibration_v2.json"
def read(p):
    try:return json.loads(p.read_text())
    except:return None
def main():
    cs=read(C) or []; rows=[]
    if J.exists():
        for line in J.read_text().splitlines():
            try: rows.append(json.loads(line))
            except: pass
    out={}
    for m in range(1,6):
        vals=[]
        for r in rows:
            try:
                issue=float(r["issued_at"]); p0=float(r["price"]); f=next(x for x in r["forecasts"] if int(x["minutes"])==m)
            except: continue
            future=[c for c in cs if float(c.get("timestamp",0))>=issue+m*60]
            if not future or p0<=0: continue
            cl=float(future[0].get("close",0)); actual=(cl/p0-1)*100
            prob=float(f.get("probability_up",.5)); direction=1 if prob>=.5 else -1
            vals.append((actual,direction,prob,float(f.get("expected_return_pct",0))))
        n=len(vals); correct=sum(1 for a,d,_,_ in vals if (a>=0)==(d==1))
        signed=[a*d for a,d,_,_ in vals]
        aligned=[a*d for a,d,_,_ in vals if abs(a)>0]
        mae=[abs(a-er) for a,_,_,er in vals]
        brier=[(p-(1 if a>=0 else 0))**2 for a,_,p,_ in vals]
        out[str(m)]={"samples":n,"directional_accuracy":correct/n if n else None,
                     "mean_signed_return_pct":sum(signed)/n if n else None,
                     "mean_aligned_move_pct":sum(aligned)/n if n else None,
                     "mae_return_pct":sum(mae)/n if n else None,
                     "brier_score":sum(brier)/n if n else None}
    report={"updated_at":time.time(),"total_scored":sum(x["samples"] for x in out.values()),"horizons":out,
            "minimum_samples_for_gate":30,"minimum_accuracy_for_gate":.52,
            "minimum_mean_aligned_move_pct":.015,"cost_buffer_bps":15,
            "status":"RUNNING","paper_only":True,"promotion_allowed":False}
    O.write_text(json.dumps(report,indent=2)); print(json.dumps(report,indent=2))
if __name__=="__main__": main()
