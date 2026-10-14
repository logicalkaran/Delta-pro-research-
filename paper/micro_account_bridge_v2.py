"""Non-optimistic micro-account bridge.

Uses subsequent recorded 1m candles to resolve stop/target outcomes.
No synthetic exits and no exchange orders.
"""
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from paper.micro_account_paper_v2 import load,save,simulate
LEDGER=ROOT/"data/processed/institutional_absorption_monitor_v2.jsonl"
CURSOR=ROOT/"data/processed/micro_account_bridge_v2.cursor"
CANDLES=ROOT/"data/processed/delta_1m.jsonl"

def candles():
    out=[]
    if CANDLES.exists():
        for x in CANDLES.read_text().splitlines():
            try:
                r=json.loads(x)
                if all(k in r for k in ("timestamp","open","high","low")): out.append(r)
            except Exception: pass
    return out

def main():
    lines=LEDGER.read_text().splitlines() if LEDGER.exists() else []
    offset=int(CURSOR.read_text()) if CURSOR.exists() else 0
    cs=candles(); s=load(); processed=0; unresolved=0
    for raw in lines[offset:]:
        try: row=json.loads(raw)
        except Exception: continue
        ev=row.get("event")
        if not isinstance(ev,dict) or ev.get("event")!="ENTRY": continue
        side=str(ev.get("action",ev.get("side", ""))).upper(); entry=float(ev.get("entry",0))
        stop=float(ev.get("stop",0)); target=float(ev.get("target",0))
        ts=float(ev.get("entry_candle",ev.get("timestamp",ev.get("ts",0))) or 0)
        if side not in ("LONG","SHORT") or not entry or not stop or not target: continue
        future=[c for c in cs if float(c["timestamp"])>ts]
        if not future:
            unresolved+=1; continue
        outcome=None
        for c in future[:30]:
            hi=float(c["high"]); lo=float(c["low"])
            hit_stop=(lo<=stop) if side=="LONG" else (hi>=stop)
            hit_target=(hi>=target) if side=="LONG" else (lo<=target)
            if hit_stop and hit_target: outcome="STOP_FIRST_CONSERVATIVE"; exit_px=stop; break
            if hit_stop: outcome="STOP"; exit_px=stop; break
            if hit_target: outcome="TARGET"; exit_px=target; break
        if outcome is None:
            unresolved+=1; continue
        # Execute using the actual resolved price rather than assuming target.
        simulate(s,side,entry,stop,exit_px,entry)
        processed+=1
        if s["status"]!="ACTIVE": break
    CURSOR.write_text(str(len(lines))); save(s)
    print(json.dumps({"processed":processed,"unresolved":unresolved,
                      "state":s,"paper_only":True,
                      "execution_model":"NEXT_1M_CANDLE_PATH","optimistic_target_assumption":False},indent=2))
if __name__=="__main__": main()
