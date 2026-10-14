import importlib.util
from pathlib import Path
import numpy as np

P = Path(__file__).with_name("order_flow_confirmation_experiment_v1.py")
SPEC = importlib.util.spec_from_file_location("flow_exp", P)
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)

def test_event_origins_are_non_overlapping_and_same_session():
    rows=[]
    for i in range(30):
        rows.append(("s1",1000.0+i,100.0+i*.001,[.1,.2,.0],.1))
    events=M.make_events(rows)
    assert events
    assert all(events[i+1]["ts"]-events[i]["ts"] >= 5 for i in range(len(events)-1))
    assert all(e["session_id"]=="s1" and e["target_ts"]-e["ts"] >= 5 for e in events)

def test_logistic_probabilities_are_finite():
    X=np.array([[-1.,0.],[0.,1.],[1.,0.],[2.,1.],[-2.,-1.]])
    y=np.array([0.,1.,1.,1.,0.])
    mu,sd,w,b=M.fit_logistic(X,y,steps=100)
    p=M.sigmoid(((X-mu)/sd)@w+b)
    assert np.isfinite(p).all()
    assert ((p>0)&(p<1)).all()

def test_trade_metrics_counts_drawdown_and_expectancy():
    m=M.tmetrics([-2.,1.,-3.,2.])
    assert m["independent_trade_count"]==4
    assert m["mean_net_bps"]==-0.5
    assert m["max_drawdown_bps"]==4.0
    assert m["profit_factor"]==0.6

def test_probability_metrics_are_bounded():
    m=M.pmetrics([0,1,0,1],[.1,.8,.4,.7])
    assert 0 <= m["brier"] <= 1
    assert m["log_loss"] > 0
    assert sum(x["n"] for x in m["calibration_bins"])==4
