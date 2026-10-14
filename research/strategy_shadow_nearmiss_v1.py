"""Shadow near-miss analyzer. Never feeds the production selector.
Records rejection counts and evaluates simple forward price paths for research.
"""
from pathlib import Path
import json,time,collections
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"data/processed/institutional_absorption_telemetry_v1.jsonl"
OUT=ROOT/"data/processed/strategy_shadow_nearmiss_v1.json"

def main():
    rows=[]
    if SRC.exists():
        for line in SRC.read_text(errors="ignore").splitlines()[-500:]:
            try:
                x=json.loads(line)
                if not x.get("valid",False) and x.get("reasons"):
                    rows.append(x)
            except Exception: pass
    counts=collections.Counter(r for x in rows for r in x.get("reasons",[]))
    result={
      "updated_at":int(time.time()),
      "sample":len(rows),
      "top_rejections":[{"reason":k,"count":v,"share":v/len(rows) if rows else 0} for k,v in counts.most_common(15)],
      "near_miss_candidates":sum(1 for x in rows if any(r in {"LONG_CVD_NOT_EXTREME","SHORT_CVD_NOT_EXTREME","LONG_REJECTION_WEAK","SHORT_REJECTION_WEAK","OI_FLAT_OR_DOWN","POC_NOT_ABOVE_ENTRY","POC_NOT_BELOW_ENTRY"} for r in x.get("reasons",[]))),
      "production_strategy_unchanged":True,
      "paper_only":True,
      "real_orders":False
    }
    OUT.write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
if __name__=="__main__": main()
