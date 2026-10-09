from pathlib import Path
import json
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from research.micro_account_challenge_v1 import ChallengeConfig, size

ROOT=Path(__file__).resolve().parents[1]
LEDGER=ROOT/"data/processed/institutional_absorption_monitor_v2.jsonl"
OUT=ROOT/"data/processed/micro_account_challenge_v1.json"
CFG=ChallengeConfig()

def main():
    equity=CFG.starting_usd
    trades=0; skipped=0
    reasons={}
    if LEDGER.exists():
        for line in LEDGER.read_text().splitlines():
            if not line.strip(): continue
            try: e=json.loads(line)
            except Exception: continue
            ev=e.get("event",{})
            if isinstance(ev,str):
                continue
            if ev.get("event")!="SIGNAL": continue
            m=ev.get("metrics",{})
            entry=float(ev.get("entry") or m.get("entry") or 0)
            stop=float(ev.get("stop") or m.get("stop") or 0)
            if entry<=0 or stop<=0:
                skipped+=1; reasons["MISSING_PRICE"]=reasons.get("MISSING_PRICE",0)+1; continue
            stop_pct=abs(entry-stop)/entry
            r=size(equity,entry,stop_pct,CFG)
            if not r.allowed:
                skipped+=1; reasons[r.reason]=reasons.get(r.reason,0)+1; continue
            trades+=1
    result={"equity":round(equity,8),"target":CFG.target_usd,
            "tradeable_signals":trades,"skipped_signals":skipped,
            "skip_reasons":reasons,"paper_only":True,
            "status":"READY_FOR_LIVE_FEED" if trades else "WAITING_FOR_QUALIFYING_SIGNALS"}
    OUT.write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
if __name__=="__main__": main()
