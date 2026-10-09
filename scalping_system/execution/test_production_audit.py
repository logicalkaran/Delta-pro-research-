from execution.production_audit import audit

def test_live_is_blocked_by_current_evidence():
    r = audit()
    assert r["live_orders"] is False
    assert r["status"] == "PAPER_READY_LIVE_BLOCKED"
    assert "positive_net_edge" in r["blockers"]
    assert "profit_factor_ge_1_2" in r["blockers"]
