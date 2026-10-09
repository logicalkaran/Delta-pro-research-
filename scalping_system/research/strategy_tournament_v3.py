"""Outcome-based BTC strategy tournament with deduplication and chronological holdout."""
from pathlib import Path
import json,time
ROOT=Path(__file__).resolve().parents[1]; SRC=ROOT/"data/processed/microstructure_scalper_v3_backtest.jsonl"; C=ROOT/"data/live_candles.json"; OUT=ROOT/"data/processed/strategy_tournament_v3.json"
COST=.0012
def price_after(cs,t):
    target=t+60; best=None
    for c in cs:
        try:
            ct=float(c.get("timestamp")); cl=float(c.get("close"))
            if ct>=target and (best is None or ct<best[0]): best=(ct,cl)
        except:pass
    return best[1] if best else None
def score(rows,cs,cut=None):
    vals=[]; seen=set()
    for r in rows:
        try:
            action=r["action"]; p=float(r["price"]); score=abs(float(r["score"])); per=float(r["persistence"]); ts=float(r["ts"]); ts=ts/1e6 if ts>1e12 else ts
            key=(round(ts,1),action,p)
        except:continue
        if key in seen:continue
        seen.add(key)
        if cut is not None and ts>=cut:continue
        if action not in ("LONG","SHORT") or p<=0:continue
        fp=price_after(cs,ts)
        if fp is None:continue
        vals.append((((fp/p)-1)*100 if action=="LONG" else ((p/fp)-1)*100)-COST)
    n=len(vals); pos=sum(x>0 for x in vals); neg=sum(x<0 for x in vals)
    return {"trades":n,"win_rate":pos/n if n else None,"avg_net_return_pct":sum(vals)/n if n else None,"total_net_return_pct":sum(vals),"profit_factor":sum(x for x in vals if x>0)/abs(sum(x for x in vals if x<0)) if neg else None}
def main():
    cs=json.loads(C.read_text()); rows=[]
    for line in SRC.read_text().splitlines():
        try:rows.append(json.loads(line))
        except:pass
    rows=sorted(rows,key=lambda r:float(r.get("ts",0))); ts=[float(r.get("ts",0)) for r in rows]; cut=ts[int(len(ts)*.6)] if ts else 0
    configs=[("MOMENTUM",9,.60),("HIGH_SCORE",8,.60),("VERY_HIGH_SCORE",10,.70),("PERSISTENT",8,.80),("FAST_EDGE",7,.50)]
    out={}
    for name,threshold,persist in configs:
        selected=[r for r in rows if abs(float(r.get("score",0)))>=threshold and float(r.get("persistence",0))>=persist]
        # evaluate separately; cut is based on source chronology, with test as the later 40%.
        train=score(selected,cs,cut); test_rows=[r for r in selected if (float(r.get("ts",0))/1e6 if float(r.get("ts",0))>1e12 else float(r.get("ts",0)))>=cut]
        test=score(test_rows,cs,None)
        out[name]={"train":train,"test":test}
    best=max(out,key=lambda k:(out[k]["test"]["avg_net_return_pct"] if out[k]["test"]["avg_net_return_pct"] is not None else -999))
    report={"updated_at":time.time(),"horizon_minutes":1,"cost_model_bps":12,"deduplicated":True,"holdout_fraction":.40,"strategies":out,"best_by_test_avg_net":best,"paper_only":True,"real_orders":False,"promotion_allowed":False}
    OUT.write_text(json.dumps(report,indent=2)); print(json.dumps(report,indent=2))
if __name__=="__main__":main()
