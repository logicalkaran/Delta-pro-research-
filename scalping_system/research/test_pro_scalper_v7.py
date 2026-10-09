import json
from pathlib import Path
from research.pro_scalper_v7 import evaluate

ROOT=Path(__file__).resolve().parents[1]

def test_v7_abstains_without_confirmed_v6_edge(monkeypatch):
    import research.pro_scalper_v7 as m
    monkeypatch.setattr(m,"v6_ensemble",lambda *a,**k:{"action":"LONG","net_edge_bps":0.5})
    out=evaluate({})
    assert out["action"]=="ABSTAIN"
    assert out["reason"]=="V6_NET_EDGE_FAIL"

def test_v7_is_paper_only():
    out=evaluate({})
    assert out["paper_only"] is True
    assert out["real_orders"] is False
