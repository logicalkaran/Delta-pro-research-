"""Fail-closed live readiness bridge used by live_execution_gate.

Evaluation is deliberately side-effect-free. Run the standalone production audit
module to print the evidence report.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "execution" / "LIVE_PROMOTION_POLICY.json"


def evaluate() -> dict:
    """Evaluate readiness without modifying files or runtime state."""
    try:
        policy = json.loads(POLICY.read_text(encoding="utf-8"))
    except Exception:
        return {"eligible": False, "reasons": ["POLICY_UNREADABLE"]}

    try:
        from execution.production_audit import audit

        result = audit()
    except Exception as exc:
        return {"eligible": False, "reasons": ["AUDIT_ERROR", type(exc).__name__]}

    if result.get("status") != "PAPER_PRODUCTION_HARDENED":
        return {
            "eligible": False,
            "reasons": result.get("blockers", ["AUDIT_NOT_READY"]),
            "audit": result,
        }
    if policy.get("status") != "PROMOTED":
        return {"eligible": False, "reasons": ["POLICY_NOT_PROMOTED"], "audit": result}
    return {"eligible": True, "reasons": [], "audit": result}
