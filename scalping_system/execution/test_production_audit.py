from execution.production_audit import audit

def test_live_is_blocked_by_current_evidence():
    r = audit()
    assert r["live_orders"] is False
    assert r["status"] == "PAPER_READY_LIVE_BLOCKED"
    assert "positive_net_edge" in r["blockers"]
    assert "profit_factor_ge_1_2" in r["blockers"]


def test_real_orders_true_is_a_hard_audit_blocker(monkeypatch):
    """A paper audit must never pass when evidence says real orders were used."""
    from execution import production_audit as module

    fixtures = {
        str(module.POLICY): {"status": "PROMOTED"},
        str(module.SUMMARY): {
            "real_orders": True, "trades": 150, "avg_net_bps": 2.0,
            "profit_factor": 1.5, "win_rate": 0.6,
        },
        str(module.WALK): {"avg_net_bps": 2.0, "sum_net_bps": 300.0, "selected_trades": 150},
        str(module.REGIME): {"results": [{
            "model": "maker", "adverse_selection_bps": 1,
            "result": {"avg_net_bps": 1.0, "profit_factor": 1.3},
        }]},
    }
    monkeypatch.setattr(module, "_load", lambda path: fixtures.get(str(path), {}))

    result = module.audit()

    assert result["checks"]["paper_only"] is False
    assert "paper_only" in result["blockers"]
    assert result["status"] == "PAPER_READY_LIVE_BLOCKED"


def test_missing_paper_only_evidence_is_a_hard_audit_blocker(monkeypatch):
    """Missing paper-only evidence must fail closed rather than imply paper mode."""
    from execution import production_audit as module

    fixtures = {
        str(module.POLICY): {"status": "BLOCKED_UNTIL_VALIDATED"},
        str(module.SUMMARY): {"trades": 150, "avg_net_bps": 2.0, "profit_factor": 1.5},
        str(module.WALK): {"avg_net_bps": 2.0, "sum_net_bps": 300.0, "selected_trades": 150},
        str(module.REGIME): {"results": [{
            "model": "maker", "adverse_selection_bps": 1,
            "result": {"avg_net_bps": 1.0, "profit_factor": 1.3},
        }]},
    }
    monkeypatch.setattr(module, "_load", lambda path: fixtures.get(str(path), {}))

    result = module.audit()

    assert result["checks"]["paper_only"] is False
    assert "paper_only" in result["blockers"]
    assert result["status"] == "PAPER_READY_LIVE_BLOCKED"
