import json,sys
import pytest
from pathlib import Path
R=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(R))
from strategy.short_horizon_predictor_v1 import predict
from strategy.predictive_levels_v1 import compute_levels
from strategy.short_horizon_execution_gate_v1 import gate
state_path=R/"data/live_microstructure_state.json"; candles_path=R/"data/live_candles.json"
if not state_path.exists() or not candles_path.exists(): pytest.skip("live market-data feed intentionally stopped", allow_module_level=True)
s=json.loads(state_path.read_text()); c=json.loads(candles_path.read_text())
px=float(s["order_book"]["mid_price"]); lv=compute_levels(c,px,s["order_book"]); pr=predict(c,lv,s)
for side in ("LONG","SHORT"):
 stop=px-(lv.atr if side=="LONG" else -lv.atr)
 print(side,gate(pr,side,px,stop).__dict__)
