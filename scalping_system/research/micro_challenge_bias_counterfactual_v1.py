"""Counterfactual diagnostic for bias-rejected contest candidates."""
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[1]
LOG=ROOT/"data/processed/micro_challenge_stream_v2.jsonl"
OUT=ROOT/"data/processed/micro_challenge_bias_counterfactual_v1.json"
def main():
    rows=[]
    if LOG.exists():
        for line in LOG.read_text().splitlines():
            try: rows.append(json.loads(line))
            except: pass
    rejects=[x for x in rows if x.get("event")=="REJECT" and "BIAS_CONFLICT" in str(x.get("reason",""))]
    # Current reject events do not retain future OHLC, so do not fabricate outcomes.
    # Instead report the exact missing evidence needed for a valid counterfactual.
    report={
      "candidates":len(rejects),
      "evaluable":0,
      "wins":0,"losses":0,"timeouts":0,
      "status":"INSUFFICIENT_OUTCOME_DATA",
      "reason":"REJECT events lack future candle path/exit prices; assigning outcomes from current snapshots would introduce look-ahead or fabricated fills.",
      "required_next_step":"shadow rejected candidates with entry, stop, target and subsequent candle path, without changing live selector",
      "paper_only":True,"real_orders":False
    }
    OUT.write_text(json.dumps(report,indent=2)); print(json.dumps(report,indent=2))
if __name__=="__main__": main()
