"""Per-evaluation telemetry for institutional absorption paper monitor."""
from pathlib import Path
import json,time
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"data/processed/institutional_absorption_monitor_v2.jsonl"
OUT=ROOT/"data/processed/strategy_telemetry_v1.jsonl"

def main():
    n=0
    if not SRC.exists(): return
    with OUT.open("a") as f:
        for line in SRC.read_text().splitlines():
            try:r=json.loads(line)
            except Exception:continue
            ev=r.get("event")
            if not isinstance(ev,dict):continue
            if ev.get("event") not in ("NO_TRADE","EDGE_REJECT","EDGE_ACCEPT","SIGNAL"):continue
            t={"ts":ev.get("timestamp",ev.get("ts",time.time())),
                "event":ev.get("event"),
                "reason":ev.get("reason") or ev.get("reasons"),
                "action":ev.get("action"),
                "side":ev.get("side"),
                "regime":ev.get("regime"),
                "confidence":ev.get("confidence"),
                "edge_score":ev.get("edge_score"),
                "rr":ev.get("rr"),
                "metrics":ev.get("metrics",{})}
            f.write(json.dumps(t)+"\n");n+=1
    print(json.dumps({"telemetry_records_written":n,"paper_only":True}))
if __name__=="__main__":main()
