"""Bridge live Edge-approved paper signals into the $2 micro-account engine."""
from pathlib import Path
import json,time,sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from paper.micro_account_paper_v2 import load,save,simulate
LEDGER=ROOT/"data/processed/institutional_absorption_monitor_v2.jsonl"
CURSOR=ROOT/"data/processed/micro_account_bridge_v1.cursor"

def main():
    offset=int(CURSOR.read_text()) if CURSOR.exists() else 0
    if not LEDGER.exists(): return
    lines=LEDGER.read_text().splitlines()
    s=load(); processed=0
    for line in lines[offset:]:
        try: row=json.loads(line)
        except Exception: continue
        ev=row.get("event")
        if not isinstance(ev,dict): continue
        if ev.get("event")!="EDGE_ACCEPT": continue
        side=str(ev.get("side","")).upper()
        if side not in ("LONG","SHORT"): continue
        entry=float(ev.get("entry",0)); stop=float(ev.get("stop",0)); target=float(ev.get("target",0))
        result=simulate(s,side,entry,stop,target,entry)
        processed+=1
        if result.get("status") in ("TARGET_REACHED","HALTED_RISK"): break
    CURSOR.write_text(str(len(lines)))
    save(s)
    print(json.dumps({"processed":processed,"state":s,"paper_only":True},indent=2))
if __name__=="__main__": main()
