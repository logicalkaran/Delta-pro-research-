"""Single fail-closed gate for every real BTC order submission.

This module never submits orders. It only verifies that the independent
promotion policy, operator arm, execution switch, and kill switch permit the
caller to continue.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "execution" / "LIVE_PROMOTION_POLICY.json"
KILL = ROOT / "data" / "run" / "LIVE_KILL_SWITCH"


class LiveExecutionBlocked(RuntimeError):
    pass


def _true(name: str) -> bool:
    return os.getenv(name, "").strip().lower() == "true"


def check() -> dict:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    reasons = []

    if policy.get("status") != "PROMOTED":
        reasons.append("PROMOTION_POLICY_BLOCKED")

    # The promotion policy is not sufficient by itself. Require the independent
    # machine-readable readiness gate as well, so changing the policy/arming
    # flags cannot bypass strategy, walk-forward, cost, paper-stability,
    # risk-limit, adapter, or operator checks.
    from live_readiness_gate import evaluate
    readiness = evaluate()
    if not readiness["eligible"]:
        reasons.append("LIVE_READINESS_GATE_BLOCKED")

    if not _true("BTC_LIVE_EXECUTION"):
        reasons.append("BTC_LIVE_EXECUTION_NOT_ENABLED")
    if not _true("BTC_LIVE_OPERATOR_APPROVED"):
        reasons.append("BTC_LIVE_OPERATOR_APPROVED_NOT_ENABLED")
    if KILL.exists():
        reasons.append("LIVE_KILL_SWITCH")

    return {
        "eligible": not reasons,
        "status": "ARMED" if not reasons else "LOCKED",
        "reasons": reasons,
        "policy_status": policy.get("status"),
        "real_orders_allowed": False if reasons else True,
    }


def require() -> dict:
    result = check()
    if not result["eligible"]:
        raise LiveExecutionBlocked("LIVE_EXECUTION_GATE:" + ",".join(result["reasons"]))
    return result
