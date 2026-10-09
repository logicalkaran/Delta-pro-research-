"""Diagnose why the paper strategy is not producing accepted signals."""
from pathlib import Path
import json,collections,time
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"data/processed/institutional_absorption_monitor_v2.jsonl"
OUT=ROOT/"data/processed/strategy_rejection_diagnostics_v1.json"

def main():
    counts=collections.Counter(); samples={}
    total=0
    if SRC.exists():
        for line in SRC.read_text().splitlines():
            try:r=json.loads(line)
            except Exception:continue
            ev=r.get("event")
            if isinstance(ev,dict):
                name=ev.get("event")
                payload=ev
            else:
                name=ev
                payload=r
            if name in ("NO_TRADE","EDGE_REJECT"):
                total+=1
                reasons=payload.get("reason") or payload.get("reasons") or [payload.get("reason_code","UNKNOWN")]
                if isinstance(reasons,str): reasons=[reasons]
                for reason in reasons:
                    key=str(reason);counts[key]+=1
                    samples.setdefault(key,payload)
    ranked=counts.most_common()
    result={"generated_at":time.time(),"evaluations":total,
            "rejection_reasons":[{"reason":k,"count":v,"share":v/total if total else 0} for k,v in ranked],
            "top_reason":ranked[0][0] if ranked else None,
            "accepted_signals":0,"paper_only":True,"real_orders":False,
            "interpretation":"COLLECT_MORE_DATA" if total<100 else "REVIEW_TOP_REJECTIONS"}
    OUT.write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
if __name__=="__main__":main()
