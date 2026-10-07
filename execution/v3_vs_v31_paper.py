"""Parallel V3 vs V3.1 live-paper evaluator. Never submits orders."""
import json,time,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from strategy.microstructure_scalper_v3 import evaluate as v3
from strategy.microstructure_scalper_v3_1 import evaluate as v31
STATE=ROOT/"data/live_microstructure_state.json"
OUT=ROOT/"data/processed/v3_vs_v31_paper.jsonl"
last=None
print("V3/V3.1 COMPARISON WATCHER | REAL ORDERS OFF",flush=True)
while True:
    try:
        s=json.loads(STATE.read_text())
        a=v3(s); b=v31(s); key=(a.action,b["action"])
        if key!=last:
            row={"ts":time.time(),"v3":{"action":a.action,"score":a.score,"expected":a.expected_move_pct},"v31":b}
            OUT.parent.mkdir(parents=True,exist_ok=True)
            with OUT.open("a") as f:f.write(json.dumps(row,separators=(",",":"))+"\n")
            print("COMPARE",json.dumps(row,separators=(",",":")),flush=True); last=key
    except Exception as e: print("COMPARE_ERROR",e,flush=True)
    time.sleep(.5)
