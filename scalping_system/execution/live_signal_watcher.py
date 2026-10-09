"""Continuous V3 signal watcher. Generates candidates only; never submits orders."""
import json,time,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
STATE=ROOT/"data/live_microstructure_state.json"
OUT=ROOT/"data/processed/live_trade_candidates.jsonl"

def check(s):
    w5=s["windows"]["5"]; w30=s["windows"]["30"]; ob=s["order_book"]; q=s["quality"]
    common=w5["trades"]>=4 and q["fresh_seconds"]<=2
    long=common and w5["delta_pct"]>=.12 and w30["delta_pct"]>=.08 and ob["imbalance_5"]>=.12 and s["price"]["5"]["return_pct"]>=.025
    short=common and w5["delta_pct"]<=-.12 and w30["delta_pct"]<=-.08 and ob["imbalance_5"]<=-.12 and s["price"]["5"]["return_pct"]<=-.025
    if long:return "LONG"
    if short:return "SHORT"
    return None

last=None
print("V3 CONTINUOUS PAPER WATCHER STARTED | REAL ORDERS OFF | 1 HOUR STUDY",flush=True)
while True:
    try:
        s=json.loads(STATE.read_text())
        side=check(s)
        if side and side!=last:
            p=float(s["order_book"]["mid_price"])
            # Candidate only. Stop/target must be derived from the next validated execution plan.
            row={"ts":time.time(),"side":side,"reference_entry":p,
                 "rr":"1:2","contracts":1,"status":"CANDIDATE_NOT_SUBMITTED"}
            OUT.parent.mkdir(parents=True,exist_ok=True)
            with OUT.open("a") as f:f.write(json.dumps(row,separators=(",",":"))+"\n")
            print("CANDIDATE",json.dumps(row,separators=(",",":")),flush=True)
        last=side
    except Exception as e:
        print("WATCH_ERROR",e,flush=True)
    time.sleep(.5)
