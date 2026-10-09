"""Fail-closed supervisor for the paper trading stack."""
from pathlib import Path
import json,subprocess,time
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data/processed/paper_supervisor_v1.json"; STATE=ROOT/"data/processed/micro_account_paper_v2_state.json"
REQUIRED=["data/live_microstructure_state.json","execution/LIVE_PROMOTION_POLICY.json","paper/institutional_absorption_monitor_v2.py","paper/micro_account_paper_v2.py","paper/micro_account_bridge_v2.py","paper/micro_challenge_monitor_v1.py","research/production_readiness_gate_v1.py"]
def main():
    now=time.time(); missing=[x for x in REQUIRED if not (ROOT/x).exists()]
    checks={"files":not missing,"missing":missing}
    try:
        m=json.loads((ROOT/"data/live_microstructure_state.json").read_text()); age=now-float(m.get("updated_at_epoch",m.get("timestamp",0))); checks["microstructure_age_seconds"]=round(age,3); checks["microstructure_fresh"]=age<=5
    except Exception as e: checks["microstructure_fresh"]=False; checks["microstructure_error"]=str(e)
    try:
        p=json.loads((ROOT/"execution/LIVE_PROMOTION_POLICY.json").read_text()); checks["live_blocked"]=p.get("status")=="BLOCKED_UNTIL_VALIDATED" and p.get("paper_only_until_all_conditions_pass") is True
    except Exception: checks["live_blocked"]=False
    try:
        s=json.loads(STATE.read_text()) if STATE.exists() else {}; checks["micro_account_status"]=s.get("status","MISSING"); checks["equity"]=s.get("equity")
    except Exception: checks["micro_account_status"]="ERROR"
    try:
        ps=subprocess.run(["ps","-ef"],capture_output=True,text=True,timeout=2).stdout
        checks["monitor_process_alive"]="institutional_absorption_monitor_v2.py" in ps
        checks["delta_process_alive"]="delta_collector.websocket_client_v2" in ps
        checks["challenge_process_alive"]=("micro_challenge_monitor_v2.py" in ps) or ("micro_challenge_monitor_v1.py" in ps)
    except Exception:
        checks["monitor_process_alive"]=checks["delta_process_alive"]=checks["challenge_process_alive"]=False
    healthy=checks["files"] and checks["microstructure_fresh"] and checks["live_blocked"] and checks["monitor_process_alive"] and checks["delta_process_alive"] and checks["challenge_process_alive"]
    result={"timestamp":now,"status":"HEALTHY_PAPER" if healthy else "HALT_FAIL_CLOSED","checks":checks,"paper_only":True,"real_orders":False,"live_enabled":False}
    OUT.write_text(json.dumps(result,indent=2)); print(json.dumps(result,indent=2))
if __name__=="__main__":main()
