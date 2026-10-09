import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from research.ml_scalper_v1 import train

def test_ml_train_is_research_only():
    rows=[
      {"issued_at":i,"delta5":0.1,"delta30":0.1,"imbalance":0.2,"return5":0.01,
       "net_return_pct":0.02 if i%2==0 else -0.01}
      for i in range(300)
    ]
    m=train(rows)
    assert m["status"]=="RESEARCH_ONLY"
    assert m["auto_apply"] is False
    assert m["paper_only"] is True
    assert m["real_orders"] is False

def test_live_gate_fails_closed():
    from execution.live_readiness_gate import evaluate
    r=evaluate()
    assert r["eligible"] is False
