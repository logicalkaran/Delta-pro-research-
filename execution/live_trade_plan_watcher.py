"""Candidate-to-plan validator. Never submits orders."""
import json,time
from pathlib import Path
from live_trade_guard import TradePlan,GuardConfig,validate,round_tick
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"data/processed/live_trade_candidates.jsonl"
OUT=ROOT/"data/processed/live_trade_plans.jsonl"
seen=0
print("TRADE PLAN VALIDATOR STARTED | EXECUTION OFF",flush=True)
while True:
    try:
        if not SRC.exists():
            time.sleep(.5); continue
        lines=SRC.read_text().splitlines()
        while seen<len(lines):
            row=json.loads(lines[seen]); seen+=1
            entry=round_tick(float(row["reference_entry"]))
            # Conservative fixed price risk for the tiny account; guard rejects if fees/risk exceed limits.
            risk=round_tick(250.0)
            if row["side"]=="LONG":
                stop=round_tick(entry-risk); target=round_tick(entry+risk*2)
            else:
                stop=round_tick(entry+risk); target=round_tick(entry-risk*2)
            plan=TradePlan(row["side"],entry,stop,target,1)
            ok,detail=validate(plan,GuardConfig(rr=2.0))
            result={"ts":time.time(),"candidate":row,"plan":plan.__dict__,
                    "status":"READY_FOR_EXPLICIT_ENABLE" if ok else "BLOCKED",
                    "risk_check":detail,"execution":"NOT_SUBMITTED"}
            OUT.parent.mkdir(parents=True,exist_ok=True)
            with OUT.open("a") as f:f.write(json.dumps(result,separators=(",",":"))+"\n")
            print("PLAN",json.dumps(result,separators=(",",":")),flush=True)
    except Exception as e: print("PLAN_ERROR",e,flush=True)
    time.sleep(.5)
