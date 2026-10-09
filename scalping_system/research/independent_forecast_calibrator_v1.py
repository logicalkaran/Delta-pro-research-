"""Causal independent edge calibration; research/paper only."""
from collections import defaultdict
from pathlib import Path
import json, math, time
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"data/processed/strategy_forward_tournament_v1.jsonl"
OUT=ROOT/"data/processed/independent_forecast_calibration_v1.json"
MIN_TRAIN=20
def load():
    if not SRC.exists(): return []
    a=[]
    for line in SRC.read_text().splitlines():
        try:
            r=json.loads(line)
            if float(r.get("issued_at",0))>0 and r.get("net_return_pct") is not None: a.append(r)
        except Exception: pass
    return sorted(a,key=lambda r:float(r["issued_at"]))
def b(x,cuts):
    x=float(x)
    for i,c in enumerate(cuts):
        if x<c:return i
    return len(cuts)
def key(r):
    d=float(r.get("delta5",0)); i=float(r.get("imbalance",0)); q=float(r.get("return5",0))
    return (int(r.get("horizon",0)),str(r.get("regime","?")),1 if d>0 else -1 if d<0 else 0,
            b(d,(-.30,-.15,-.05,.05,.15,.30)),b(i,(-.60,-.30,-.10,.10,.30,.60)),
            b(q,(-.15,-.05,-.02,.02,.05,.15)))
def add(s,r):
    v=float(r["net_return_pct"]); x=s[key(r)]; x[0]+=1; x[1]+=v; x[2]+=v*v; x[3]+=v>0
def pred(s,r):
    x=s.get(key(r))
    if not x or x[0]<MIN_TRAIN:return None
    n,total,sq,w=x; m=total/n
    se=math.sqrt(max(0,sq/n-m*m)/n) if n>1 else 1e9
    return (m-1.28*se)*100,w/n,n
def main():
    rows=load(); split=int(len(rows)*.8); train=defaultdict(lambda:[0,0.,0.,0])
    for r in rows[:split]: add(train,r)
    scored=[]
    for r in rows[split:]:
        p=pred(train,r)
        if p: scored.append((p[0],float(r["net_return_pct"])*100))
    n=len(scored); mae=sum(abs(a-y) for a,y in scored)/n if n else None
    corr=None
    if n>1:
        xa=sum(a for a,_ in scored)/n; ya=sum(y for _,y in scored)/n
        num=sum((a-xa)*(y-ya) for a,y in scored); dx=sum((a-xa)**2 for a,y in scored); dy=sum((y-ya)**2 for a,y in scored)
        corr=num/math.sqrt(dx*dy) if dx and dy else None
    stress=[]
    for extra in (0,2,4,8):
        z=[y for a,y in scored if a>extra]
        stress.append({"extra_cost_bps":extra,"samples":len(z),"avg_actual_net_bps":sum(z)/len(z) if z else None,
                       "positive_rate":sum(y>0 for y in z)/len(z) if z else None})
    out={"updated_at":time.time(),"source_rows":len(rows),"holdout_rows":len(rows)-split,
         "scored_holdout":n,"mae_bps":mae,"correlation":corr,"stress":stress,
         "method":{"features":["horizon","regime","delta5","imbalance","return5"],"min_train":MIN_TRAIN,
                   "shrinkage":1.28,"paper_only":True,"real_orders":False,"promotion_allowed":False}}
    OUT.write_text(json.dumps(out,indent=2)); print(json.dumps(out,indent=2))
if __name__=="__main__":main()
