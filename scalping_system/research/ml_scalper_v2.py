"""ML Scalper V2: cost-aware return ranking with chronological holdout."""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"data/processed/strategy_forward_tournament_v1.jsonl"
OUT=ROOT/"data/processed/ml_scalper_v2_model.json"
FEATURES=("delta5","delta30","imbalance","return5")
COST_BPS=12.0

def load():
    rows=[]
    with SRC.open() as f:
        for line in f:
            if line.strip():
                r=json.loads(line)
                if all(k in r for k in FEATURES) and "gross_return_pct" in r:
                    rows.append(r)
    rows.sort(key=lambda r:float(r["issued_at"]))
    return rows

def fit(rows):
    cut=int(len(rows)*.70); tr=rows[:cut]; te=rows[cut:]
    X=np.array([[float(r[f]) for f in FEATURES] for r in tr]); y=np.array([float(r["gross_return_pct"])*100 for r in tr])
    mu=X.mean(0); sd=np.where(X.std(0)<1e-12,1,X.std(0)); Z=(X-mu)/sd
    # Ridge regression for expected gross return. Net ranking subtracts fixed conservative costs.
    A=Z.T@Z+1.0*np.eye(Z.shape[1]); w=np.linalg.solve(A,Z.T@y)
    def ev(rs):
        xx=np.array([[float(r[f]) for f in FEATURES] for r in rs]); zz=(xx-mu)/sd
        pred=zz@w
        actual=np.array([float(r["gross_return_pct"])*100-COST_BPS for r in rs])
        # Select only the predicted positive-net tail, with top-quintile diagnostic.
        mask=pred>COST_BPS
        sel=actual[mask]
        q=max(1,int(len(actual)*.20))
        idx=np.argsort(pred)[-q:]
        top=actual[idx]
        wins=sel[sel>0]; losses=-sel[sel<0]
        tw=top[top>0]; tl=-top[top<0]
        return {
          "n":len(rs),"selected":int(mask.sum()),
          "coverage":float(mask.mean()),
          "selected_avg_net_bps":float(sel.mean()) if len(sel) else 0,
          "selected_win_rate":float((sel>0).mean()) if len(sel) else 0,
          "selected_pf":float(wins.sum()/losses.sum()) if losses.sum()>0 else 0,
          "top20_avg_net_bps":float(top.mean()),
          "top20_win_rate":float((top>0).mean()),
          "top20_pf":float(tw.sum()/tl.sum()) if tl.sum()>0 else 0
        }
    return {"version":"ml_scalper_v2","features":FEATURES,"cost_bps":COST_BPS,
            "train":ev(tr),"test":ev(te),"weights":w.tolist(),"mean":mu.tolist(),"std":sd.tolist(),
            "objective":"predict gross return; rank by predicted net return after conservative cost",
            "auto_apply":False,"paper_only":True,"real_orders":False,"status":"RESEARCH_ONLY"}

def main():
    r=fit(load()); OUT.write_text(json.dumps(r,indent=2)); print(json.dumps(r,indent=2))
if __name__=="__main__": main()
