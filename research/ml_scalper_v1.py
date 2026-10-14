"""Local ML scalper V1: lightweight NumPy logistic model, research/shadow only."""
from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"data/processed/strategy_forward_tournament_v1.jsonl"
MODEL=ROOT/"data/processed/ml_scalper_v1_model.json"

FEATURES=("delta5","delta30","imbalance","return5")

def load_rows():
    rows=[]
    with SRC.open() as f:
        for line in f:
            if line.strip():
                r=json.loads(line)
                if all(k in r for k in FEATURES) and "net_return_pct" in r:
                    rows.append(r)
    rows.sort(key=lambda r:float(r["issued_at"]))
    return rows

def _standardize(x):
    mu=x.mean(axis=0); sd=x.std(axis=0); sd=np.where(sd<1e-12,1.0,sd)
    return (x-mu)/sd,mu,sd

def _sigmoid(z):
    z=np.clip(z,-40,40)
    return 1/(1+np.exp(-z))

def train(rows, train_frac=.70, epochs=800, lr=.03, l2=.01):
    n=len(rows); cut=int(n*train_frac)
    tr=rows[:cut]; te=rows[cut:]
    x=np.array([[float(r[f]) for f in FEATURES] for r in tr],dtype=float)
    y=np.array([1.0 if float(r["net_return_pct"])>0 else 0.0 for r in tr])
    z,mu,sd=_standardize(x)
    X=np.column_stack([np.ones(len(z)),z])
    w=np.zeros(X.shape[1])
    for _ in range(epochs):
        p=_sigmoid(X@w)
        grad=(X.T@(p-y))/len(y)
        grad[1:]+=l2*w[1:]
        w-=lr*grad
    def score(rs):
        xx=np.array([[float(r[f]) for f in FEATURES] for r in rs],dtype=float)
        zz=(xx-mu)/sd; XX=np.column_stack([np.ones(len(zz)),zz])
        pp=_sigmoid(XX@w)
        actual=np.array([float(r["net_return_pct"])*100 for r in rs])
        pred=pp>=.5
        selected=actual[pred]
        wins=selected[selected>0]; losses=-selected[selected<0]
        return {
            "n":len(rs),"selected":int(pred.sum()),
            "coverage":float(pred.mean()) if len(pred) else 0,
            "avg_selected_net_bps":float(selected.mean()) if len(selected) else 0,
            "win_rate":float((selected>0).mean()) if len(selected) else 0,
            "profit_factor":float(wins.sum()/losses.sum()) if losses.sum()>0 else (float("inf") if wins.sum()>0 else 0),
            "brier":float(np.mean((pp-(actual>0))**2)) if len(rs) else 0,
        }
    return {
        "version":"ml_scalper_v1",
        "features":FEATURES,
        "train":score(tr),"test":score(te),
        "weights":w.tolist(),"mean":mu.tolist(),"std":sd.tolist(),
        "threshold":0.5,
        "auto_apply":False,"paper_only":True,"real_orders":False,
        "status":"RESEARCH_ONLY"
    }

def main():
    rows=load_rows()
    model=train(rows)
    MODEL.write_text(json.dumps(model,indent=2))
    print(json.dumps({"status":model["status"],"train":model["train"],"test":model["test"]},indent=2))
if __name__=="__main__": main()
