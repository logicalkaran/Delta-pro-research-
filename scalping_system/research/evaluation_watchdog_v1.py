"""Live evaluation watchdog: confirms the monitor is producing evaluation telemetry."""
from pathlib import Path
import json,time
ROOT=Path(__file__).resolve().parents[1]
LEDGER=ROOT/"data/processed/institutional_absorption_monitor_v2.jsonl"
OUT=ROOT/"data/processed/evaluation_watchdog_v1.json"

def main():
    now=time.time(); total=0; recent=0; last_ts=0; events={}
    if LEDGER.exists():
        for line in LEDGER.read_text().splitlines():
            try:r=json.loads(line)
            except Exception:continue
            ev=r.get("event")
            if isinstance(ev,dict):
                name=str(ev.get("event",""))
                ts=float(ev.get("timestamp",ev.get("ts",r.get("ts",0))) or 0)
            else:
                name=str(ev or "")
                ts=float(r.get("ts",0) or 0)
            if name: events[name]=events.get(name,0)+1
            if ts: last_ts=max(last_ts,ts)
            if name in ("NO_TRADE","EDGE_REJECT","EDGE_ACCEPT","SIGNAL","DUPLICATE_SIGNAL_BAR"):
                total+=1
                if now-ts<=900: recent+=1
    age=now-last_ts if last_ts else None
    status="OBSERVING" if recent>0 else "NO_RECENT_EVALUATIONS"
    result={"timestamp":now,"status":status,"total_evaluation_events":total,
            "events_last_15m":recent,"last_event_age_seconds":age,
            "event_counts":events,"paper_only":True,"real_orders":False}
    OUT.write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
if __name__=="__main__":main()
