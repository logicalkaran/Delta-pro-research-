"""Read-only production readiness audit. Never enables or submits live orders."""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "execution" / "LIVE_PROMOTION_POLICY.json"
SUMMARY = ROOT / "data" / "processed" / "live_execution_paper_v3_summary.json"
WALK = ROOT / "data" / "processed" / "scalper_walkforward_selector_v1.json"
REGIME = ROOT / "data" / "processed" / "regime_execution_validation_v1.json"

def _load(p):
    try: return json.loads(p.read_text())
    except Exception: return {}

def audit():
    policy = _load(POLICY); summary = _load(SUMMARY); walk = _load(WALK); regime = _load(REGIME)
    checks = {
        "promotion_policy_locked": policy.get("status") == "BLOCKED_UNTIL_VALIDATED",
        "paper_only": summary.get("real_orders") is False,
        "minimum_100_completed_trades": int(summary.get("trades", 0)) >= 100,
        "positive_net_edge": float(summary.get("avg_net_bps", -999)) > 0,
        "profit_factor_ge_1_2": float(summary.get("profit_factor") if summary.get("profit_factor") is not None else -1) >= 1.2,
        "positive_walk_forward": float(walk.get("avg_net_bps", -999)) > 0 and float(walk.get("sum_net_bps", -999)) > 0,
        "walk_forward_sample_sufficient": int(walk.get("selected_trades", 0)) >= 100,
    }
    robust = []
    for row in regime.get("results", []):
        if row.get("model") == "maker" and row.get("adverse_selection_bps") == 1:
            result = row.get("result", {})
            robust.append(float(result.get("avg_net_bps", -999)) > 0 and float(result.get("profit_factor", -1)) >= 1.2)
    checks["adverse_selection_1bps_robust"] = any(robust)
    # A failed paper-only invariant is a hard blocker. Do not exclude it merely
    # because the current live promotion policy is independently locked.
    blockers = [k for k, v in checks.items() if not v and k != "promotion_policy_locked"]
    return {
        "status": "PAPER_PRODUCTION_HARDENED" if not blockers else "PAPER_READY_LIVE_BLOCKED",
        "live_orders": False,
        "checks": checks,
        "blockers": blockers,
        "current_paper_metrics": {
            "trades": summary.get("trades"),
            "win_rate": summary.get("win_rate"),
            "avg_net_bps": summary.get("avg_net_bps"),
            "profit_factor": summary.get("profit_factor"),
        },
    }

if __name__ == "__main__":
    print(json.dumps(audit(), indent=2))
