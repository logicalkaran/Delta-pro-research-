"""V4.4 cross-venue lead/lag evaluator.
Research-only. Requires timestamped V4.3 observations.
"""
import json,math,sys
from collections import defaultdict

PATH="data/processed/cross_venue_btc_v43.jsonl"
HORIZONS=(5,10,30,60)

def load(path=PATH):
    rows=[]
    try:
        with open(path) as f:
            for line in f:
                try:
                    r=json.loads(line); c=r.get("comparison",{})
                    if r.get("venues_ok",0)>=2 and c.get("valid"):
                        rows.append(r)
                except Exception: pass
    except FileNotFoundError: pass
    return rows

def evaluate(rows,horizon,threshold_bps=0.5):
    # V4.3 samples are ~5s apart. Match nearest future observation by epoch_ms.
    out=[]
    for i,r in enumerate(rows):
        ts=r["epoch_ms"]; edge=r.get("edge_v42",{})
        spread=float(edge.get("spread_bps") or 0)
        leader=edge.get("leader"); lagger=edge.get("lagger")
        if not leader or not lagger or spread<threshold_bps: continue
        target=ts+horizon*1000
        best=None; bestdist=10**18
        for j in range(i+1,len(rows)):
            t=rows[j]["epoch_ms"]
            dist=abs(t-target)
            if dist<bestdist: best,bestdist=rows[j],dist
            if t>target+horizon*1000: break
        if best is None or bestdist>3000: continue
        vp={x["venue"]:x["price"] for x in best["comparison"]["venues"]}
        p0={x["venue"]:x["price"] for x in r["comparison"]["venues"]}
        if "delta" not in vp or "delta" not in p0: continue
        ret=(vp["delta"]/p0["delta"]-1)*10000
        # Leader premium > lagger means leader is relatively expensive.
        # Hypothesis: divergence mean-reverts => lagger direction is opposite leader premium.
        sign=-1 if leader!=lagger else 0
        pred=sign
        signed=ret*pred
        out.append({"ret_bps":ret,"signed_bps":signed,"spread_bps":spread,
                    "leader":leader,"lagger":lagger})
    if not out: return {"n":0,"horizon_s":horizon}
    wins=sum(x["signed_bps"]>0 for x in out)
    vals=[x["signed_bps"] for x in out]
    return {"n":len(out),"horizon_s":horizon,"win_rate":wins/len(out),
            "avg_signed_bps":sum(vals)/len(vals),
            "median_signed_bps":sorted(vals)[len(vals)//2],
            "total_signed_bps":sum(vals),
            "max_win_bps":max(vals),"max_loss_bps":min(vals)}

def main():
    rows=load()
    result={"samples":len(rows),"results":[evaluate(rows,h) for h in HORIZONS]}
    print(json.dumps(result,indent=2))
    with open("data/processed/cross_venue_v44_leadlag.json","w") as f:
        json.dump(result,f,indent=2)
if __name__=="__main__": main()
