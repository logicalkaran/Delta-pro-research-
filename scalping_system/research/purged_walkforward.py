"""Purged/embargoed chronological validation for short-horizon labels."""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
from probabilistic_model import ProbabilisticModel
from market_edge_features import enrich

def load_labeled(path):
    rows=[]
    for line in Path(path).read_text().splitlines():
        try: rows.append(json.loads(line))
        except: pass
    rows.sort(key=lambda x:float(x['ts'])); out=[]; prev={}
    for r in rows:
        x=enrich(r,prev); prev=r
        mv=float(r.get('labels',{}).get('60',{}).get('move_bps',0) or 0)
        # Label only economically meaningful direction; flat is excluded from binary training.
        if abs(mv)>=1.0: x['target']=1 if mv>0 else 0; x['move_bps']=mv; out.append(x)
    return out

def evaluate(rows,horizon='60',folds=5,embargo=5):
    n=len(rows); results=[]
    for k in range(1,folds+1):
        train_end=int(n*(k/(folds+1))); test_end=int(n*((k+1)/(folds+1)))
        train=rows[:max(0,train_end-embargo)]; test=rows[train_end+embargo:test_end]
        if len(train)<100 or len(test)<30: continue
        model=ProbabilisticModel().fit(train,[r['target'] for r in train])
        p=model.predict_proba(test); y=np.asarray([r['target'] for r in test]); moves=np.asarray([r['move_bps'] for r in test])
        acc=float(np.mean((p>=.5)==y)); brier=float(np.mean((p-y)**2)); direction=np.where(p>=.5,1,-1); gross=float(np.mean(direction*moves));
        results.append({'fold':k,'train':len(train),'test':len(test),'accuracy':acc,'brier':brier,'gross_bps':gross})
    return {'folds':results,'folds_positive':sum(x['gross_bps']>0 for x in results),'fold_count':len(results),'mean_accuracy':float(np.mean([x['accuracy'] for x in results])) if results else None,'mean_gross_bps':float(np.mean([x['gross_bps'] for x in results])) if results else None}

if __name__=='__main__':
    p=Path('data/processed/live_microstructure_labeled_v1.jsonl'); print(json.dumps(evaluate(load_labeled(p)),indent=2))
