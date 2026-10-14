"""Audit $2->$4 contest gate pressure without changing trading rules."""
from pathlib import Path
import json,collections
ROOT=Path(__file__).resolve().parents[1]
LOG=ROOT/"data/processed/micro_challenge_stream_v2.jsonl"
OUT=ROOT/"data/processed/micro_challenge_gate_audit_v1.json"
def main():
    rows=[]
    if LOG.exists():
        for line in LOG.read_text().splitlines():
            try: rows.append(json.loads(line))
            except: pass
    rej=[x for x in rows if x.get("event")=="REJECT"]
    cnt=collections.Counter(x.get("reason","UNKNOWN") for x in rej)
    total=len(rej)
    report={
      "contest":"DELTA_BTCUSD_2_TO_4",
      "purpose":"diagnostic_only_no_strategy_changes",
      "rejections":total,
      "reason_counts":cnt.most_common(),
      "reason_share_pct":{k:round(v*100/total,2) for k,v in cnt.items()} if total else {},
      "interpretation":"No gate is loosened automatically. A dominant rejection reason must be validated against realized outcomes before any policy change.",
      "paper_only":True,
      "real_orders":False
    }
    OUT.write_text(json.dumps(report,indent=2)); print(json.dumps(report,indent=2))
if __name__=="__main__": main()
