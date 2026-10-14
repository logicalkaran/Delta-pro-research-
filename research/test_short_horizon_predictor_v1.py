import json,sys
import pytest
from pathlib import Path
R=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(R))
from strategy.short_horizon_predictor_v1 import predict
from strategy.predictive_levels_v1 import compute_levels
state_path=R/"data/live_microstructure_state.json"; candles_path=R/"data/live_candles.json"
if not state_path.exists() or not candles_path.exists(): pytest.skip("live market-data feed intentionally stopped", allow_module_level=True)
s=json.loads(state_path.read_text())
c=json.loads(candles_path.read_text())
ob=s.get("order_book",{}); px=float(ob.get("mid_price",0))
lv=compute_levels(c,px,ob)
print(json.dumps(predict(c,lv,s).to_dict(),indent=2))
