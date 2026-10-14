"""Out-of-sample regime analysis for short-horizon forecasts. Research only."""
from pathlib import Path
import json,time
ROOT=Path(__file__).resolve().parents[1]; J=ROOT/"data/processed/short_horizon_forecasts_v1.jsonl"; C=ROOT/"data/live_candles.json"; O=ROOT/"data/processed/short_horizon_regime_eval_v1.json"
def load(p):
    try:return json.loads(p.read_text())
    except:return None
def main():
    rows=[]; cs=load(C) or []
    if J.exists():
        for line in J.read_text().splitlines():
            try: rows.append(json.loads(line))
            except: pass
    buckets={}
    for r in rows:
        try:p0=float(r["price"]); issue=float(r["issued_at"]); regime=r.get("regime","UNKNOWN")
        except:continue
        future=[x for x in cs if float(x.get("timestamp",0))>=issue+120]
        if not future or p0<=0:continue
        actual=(float(future[0].get("close",0))/p0-1)*100
        f=next((x for x in r.get("forecasts",[]) if int(x.get("minutes",0))==2),None)
        if not f:continue
        direction=1 if float(f.get("probability_up",.5))>=.5 else -1
        z=buckets.setdefault(regime,[]); z.append((actual,direction))
    out={}
    for k,v in buckets.items():
        n=len(v); acc=sum((a>=0)==(d==1) for a,d in v)/n if n else 0
        aligned=sum(a*d for a,d in v)/n if n else 0
        out[k]={"samples":n,"directional_accuracy":acc,"mean_aligned_move_pct":aligned}
    O.write_text(json.dumps({"updated_at":time.time(),"horizon_minutes":2,"regimes":out,"paper_only":True,"promotion_allowed":False},indent=2))
    print(json.dumps({"updated_at":time.time(),"horizon_minutes":2,"regimes":out,"paper_only":True},indent=2))
if __name__=="__main__":main()
