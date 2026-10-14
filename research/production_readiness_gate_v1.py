"""Production-readiness gate for the paper trading stack.

Fail-closed: this script never enables live trading.
It verifies required policy/config files, source compilation, tests,
and explicitly reports unresolved blockers.
"""
from pathlib import Path
import json, subprocess, sys

ROOT=Path(__file__).resolve().parents[1]
REQUIRED=[
 "execution/LIVE_PROMOTION_POLICY.json",
 "strategy/institutional_absorption_v1.py",
 "strategy/edge_selector_v1.py",
 "paper/institutional_absorption_monitor_v2.py",
 "research/institutional_absorption_validation_v2.py",
 "research/micro_account_challenge_v1.py",
 "research/micro_account_challenge_runner_v1.py",
 "risk/limits.py",
 "risk/sizing.py",
 "web/market_server.py",
]
def run(cmd):
    r=subprocess.run(cmd,cwd=ROOT,text=True,capture_output=True)
    return r.returncode, (r.stdout+r.stderr)[-4000:]
def main():
    checks={}
    missing=[x for x in REQUIRED if not (ROOT/x).exists()]
    checks["required_files"]={"ok":not missing,"missing":missing}
    code,out=run([sys.executable,"-m","compileall","-q","strategy","paper","research","risk","web"])
    checks["compile"]={"ok":code==0,"output":out}
    code,out=run([sys.executable,"-m","pytest","-q","strategy/test_institutional_absorption_v1.py"])
    checks["targeted_tests"]={"ok":code==0,"output":out}
    policy={}
    try: policy=json.loads((ROOT/"execution/LIVE_PROMOTION_POLICY.json").read_text())
    except Exception as e: checks["policy"]={"ok":False,"error":str(e)}
    else:
        checks["policy"]={"ok":policy.get("status")=="BLOCKED_UNTIL_VALIDATED" and policy.get("paper_only_until_all_conditions_pass") is True,
                          "status":policy.get("status"),"paper_only":policy.get("paper_only_until_all_conditions_pass")}
    blockers=[
      "Live trading remains blocked until the promotion policy is satisfied.",
      "The $2 challenge remains paper-only; minimum contract/margin feasibility must be proven for the actual venue.",
      "At least 100 labeled trades plus positive walk-forward validation are required.",
      "No production exchange order adapter is enabled by this gate."
    ]
    # Include the independent evidence audit so this wrapper cannot report
    # readiness while the economics are negative.
    code,out=run([sys.executable,"-m","execution.production_audit"])
    try: evidence=json.loads(out)
    except Exception: evidence={"status":"AUDIT_ERROR","blockers":["evidence_audit_error"]}
    checks["evidence_audit"]={"ok":code==0 and evidence.get("status")=="PAPER_PRODUCTION_HARDENED","status":evidence.get("status"),"blockers":evidence.get("blockers",[])}
    blockers.extend(evidence.get("blockers",[]))
    checks["production_status"]="PAPER_PRODUCTION_HARDENED; LIVE_BLOCKED" if not evidence.get("blockers") else "PAPER_HARDENED; LIVE_BLOCKED"
    result={"checks":checks,"blockers":sorted(set(blockers)),"real_orders":False,"live_enabled":False}
    print(json.dumps(result,indent=2))
if __name__=="__main__": main()
