import json
from pathlib import Path

from execution import live_readiness_gate as gate


def test_evaluate_does_not_write_or_create_directories(tmp_path, monkeypatch):
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"status": "BLOCKED_UNTIL_VALIDATED"}), encoding="utf-8")
    monkeypatch.setattr(gate, "POLICY", policy)

    from execution import production_audit
    monkeypatch.setattr(production_audit, "audit", lambda: {
        "status": "PAPER_READY_LIVE_BLOCKED",
        "live_orders": False,
        "blockers": ["positive_net_edge"],
    })

    def forbidden(*args, **kwargs):
        raise AssertionError("readiness evaluation attempted a filesystem write")

    monkeypatch.setattr(Path, "write_text", forbidden)
    monkeypatch.setattr(Path, "mkdir", forbidden)

    result = gate.evaluate()

    assert result["eligible"] is False
    assert result["reasons"] == ["positive_net_edge"]
    assert result["audit"]["live_orders"] is False


def test_unreadable_policy_fails_closed(monkeypatch):
    monkeypatch.setattr(gate, "POLICY", Path("/definitely/missing/policy.json"))
    result = gate.evaluate()
    assert result == {"eligible": False, "reasons": ["POLICY_UNREADABLE"]}
