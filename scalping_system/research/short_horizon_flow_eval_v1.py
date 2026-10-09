"""Conditional flow-strength evaluation for 2m forecasts. Research only."""
from pathlib import Path
import json,time
ROOT=Path(__file__).resolve().parents[1]; J=ROOT/"data/processed/short_horizon_forecasts_v1.jsonl"; C=ROOT/"data/live_candles.json"; O=ROOT/"data/processed/short_horizon_flow_eval_v1.json"
def load(p):
    try:return json.loads(p.read_text())
    except:return None
def main():
    rows=[]; cs=load(C) or []
    if J.exists():
        for line in J.read_text().splitlines():
            try:rows.append(json.loads(line))
            except:pass
    buckets={}
    for r in rows:
        try:p0=float(r["price"]); issue=float(r["issued_at"]); fs=r["forecasts"]; f=next(x for x in fs if int(x["minutes"])==2)
        except:continue
        fut=[x for x in cs if float(x.get("timestamp",0))>=issue+120]
        if not fut or p0<=0:continue
        actual=(float(fut[0].get("close",0))/p0-1)*100
        prob=float(f.get("probability_up",.5)); direction=1 if prob>=.5 else -1
        strength=abs(prob-.5)
        bucket="WEAK" if strength<.08 else ("MEDIUM" if strength<.18 else "STRONG")
        z=buckets.setdefault(bucket,[]); z.append((actual,direction))
    out={}
    for k,v in buckets.items():
        n=len(v); out[k]={"samples":n,"directional_accuracy":sum((a>=0)==(d==1) for a,d in v)/n,"mean_aligned_move_pct":sum(a*d for a,d in v)/n}
    O.write_text(json.dumps({"updated_at":time.time(),"horizon_minutes":2,"buckets":out,"paper_only":True,"promotion_allowed":False},indent=2))
    print(json.dumps({"updated_at":time.time(),"horizon_minutes":2,"buckets":out,"paper_only":True},indent=2))
if __name__=="__main__":main()
