import numpy as np
from research.flow_l5_ablation_v1 import fit, predict, metrics, select_nonoverlap

def test_logistic_fit_predict_is_bounded():
    X=np.arange(200,dtype=float).reshape(-1,1)/200
    y=(X[:,0]>.5).astype(float)
    p=predict(fit(X,y),X)
    assert np.isfinite(p).all() and ((p>=0)&(p<=1)).all()
    assert p[-1]>p[0]

def test_nonoverlap_selector_does_not_overlap_label_windows():
    rows=[]
    for i in range(100):
        rows.append({"ts":float(i),"mid":100.,"delta30":.1,"imb5":.2,"fresh":.1,
            "session_id":"s","labels":{60:{"future_ts":i+60.,"move_bps":1.}}})
    out=select_nonoverlap(rows,60)
    assert all(out[i+1]["ts"]>=out[i]["future_ts"] for i in range(len(out)-1))
    assert len(out)<=2

def test_metrics_known_values():
    m=metrics(np.array([0.,1.]),np.array([.1,.9]))
    assert abs(m["brier"]-.01)<1e-10
    assert m["n"]==2
