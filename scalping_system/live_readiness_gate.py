"""Explicit safety gate for real-money execution.

This module is intentionally locked by default. It reports readiness; it never
places an exchange order and cannot be enabled by the dashboard.
"""
from __future__ import annotations
import json, os, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent

REQUIRED = (
    "strategy_validated",
    "walk_forward_validated",
    "costs_validated",
    "paper_stability_validated",
    "risk_limits_validated",
    "execution_adapter_validated",
    "operator_approval",
)

def evaluate():
    flags = {k: os.environ.get("BTC_LIVE_GATE_" + k.upper(), "").lower() == "true" for k in REQUIRED}
    reasons = [k for k, v in flags.items() if not v]
    health = __import__("platform_health").health()
    if health["status"] != "OK":
        reasons.append("platform_health")
    locked = bool(reasons)
    return {
        "timestamp": int(time.time()),
        "live_execution": False,
        "locked": locked,
        "eligible": not locked,
        "missing_requirements": reasons,
        "requirements": flags,
        "platform_health": health["status"],
    }

if __name__ == "__main__":
    print(json.dumps(evaluate(), indent=2))
