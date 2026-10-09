"""Fail-closed live readiness bridge used by live_execution_gate."""
from __future__ import annotations
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
POLICY=ROOT/"execution/LIVE_PROMOTION_POLICY.json"
AUDIT=ROOT/"data/processed/production_audit.json"

def evaluate():
    try:
        policy=json.loads(POLICY.read_text())
    except Exception:
        return {"eligible":False,"reasons":["POLICY_UNREADABLE"]}
    try:
        from execution.production_audit import audit
        result=audit()
    except Exception as exc:
        return {"eligible":False,"reasons":["AUDIT_ERROR",type(exc).__name__]}
    AUDIT.parent.mkdir(parents=True,exist_ok=True)
    AUDIT.write_text(json.dumps(result,indent=2))
    if result.get("status")!="PAPER_PRODUCTION_HARDENED":
        return {"eligible":False,"reasons":result.get("blockers",["AUDIT_NOT_READY"])}
    if policy.get("status")!="PROMOTED":
        return {"eligible":False,"reasons":["POLICY_NOT_PROMOTED"]}
    return {"eligible":True,"reasons":[],"audit":result}
