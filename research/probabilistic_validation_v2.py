"""Research-only validation of short-horizon probabilistic forecasts."""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
from market_edge_features import enrich
from probabilistic_model import ProbabilisticModel
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'data/processed/live_microstructure_labeled_v1.jsonl'
COST_BPS=10.76
HORIZONS=(60,120,180,300)
def load(horizon=60,flat_band=3.0):
    raw=[]
    if not SRC.exists(): return raw
    for line in SRC.read_text().splitlines():
        try: raw.append(json.loads(line))
        except: pass
    raw.sort(key=lambda x:float(x.get('ts',0))); out=[]; prev={}
    for r in raw:
        mv=float(r.get('labels',{}).get(str(horizon),{}).get('move_bps',0) or 0); x=enrich(r,prev); prev=r
        if abs(mv)>=flat_band: x['target']=1 if mv>0 else 0; x['move_bps']=mv; out.append(x)
    return out
def calibration_error(p,y,bins=10):
    p=np.asarray(p); y=np.asarray(y); e=[]
    for lo,hi in zip(np.linspace(0,1,bins+1)[:-1],np.linspace(0,1,bins+1)[1:]):
        m=(p>=lo)&(p<(hi if hi<1 else hi+1e-9))
        if m.any(): e.append((float(m.mean()),float(abs(p[m].mean()-y[m].mean()))))
    return float(sum(w*err for w,err in e)/sum(w for w,_ in e)) if e else None
def run(horizon=60,folds=5,embargo=10,flat_band=3.0):
    rows=load(horizon,flat_band); n=len(rows); results=[]
    for k in range(1,folds+1):
        train_end=int(n*k/(folds+1)); test_end=int(n*(k+1)/(folds+1)); train=rows[:max(0,train_end-embargo)]; test=rows[min(n,train_end+embargo):test_end]
        if len(train)<150 or len(test)<40: continue
        m=ProbabilisticModel(l2=2.0,lr=.03,epochs=350).fit(train,[r['target'] for r in train]); p=m.predict_proba(test); y=np.asarray([r['target'] for r in test]); mv=np.asarray([r['move_bps'] for r in test]); take=(p>=.62)|(p<=.38)
        if take.any():
            direction=np.where(p[take]>=.62,1,-1); net=direction*mv[take]-COST_BPS
            results.append({'fold':k,'train':len(train),'test':len(test),'coverage':float(take.mean()),'accuracy':float(np.mean((p[take]>=.5)==y[take])),'brier':float(np.mean((p-y)**2)),'calibration_error':calibration_error(p,y),'avg_net_bps':float(net.mean()),'profit_factor':float(net[net>0].sum()/abs(net[net<0].sum())) if (net<0).any() else float('inf'),'trades':int(len(net))})
    return {'horizon':horizon,'flat_band_bps':flat_band,'cost_floor_bps':COST_BPS,'rows':n,'folds':results,'positive_folds':sum(x['avg_net_bps']>0 for x in results),'mean_net_bps':float(np.mean([x['avg_net_bps'] for x in results])) if results else None,'total_trades':sum(x['trades'] for x in results)}
if __name__=='__main__': print(json.dumps({'results':[run(h) for h in HORIZONS]},indent=2))
