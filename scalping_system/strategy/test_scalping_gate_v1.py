from strategy.scalping_features_v1 import build_features
from strategy.scalping_gate_v1 import ScalpingGateConfig, evaluate, round_trip_cost_bps
def candle(o,h,l,c,v=100): return {"open":o,"high":h,"low":l,"close":c,"volume":v}
def feature_set(side="LONG"):
    rows=[candle(100,101,99,100) for _ in range(20)]
    rows.append(candle(100,101,98,100.6,300) if side=="LONG" else candle(100,102,99,99.4,300))
    trades=[{"size":10,"side":"buy" if side=="LONG" else "sell"}]*10
    book={"best_bid":100.0,"best_ask":100.02,"bid_depth_5":1200,"ask_depth_5":400} if side=="LONG" else {"best_bid":99.98,"best_ask":100.0,"bid_depth_5":400,"ask_depth_5":1200}
    return build_features(rows,trades,book)
def test_cost_model(): assert round_trip_cost_bps(ScalpingGateConfig())==11.0
def test_missing_target_is_hard_rejection():
    d=evaluate(feature_set(),side="LONG",entry=100); assert not d.allowed and "TARGET_REQUIRED" in d.rejected
def test_wrong_side_target_rejected():
    d=evaluate(feature_set(),side="LONG",entry=100,target=99); assert not d.allowed and "TARGET_ON_WRONG_SIDE" in d.rejected
def test_wide_spread_rejected_even_with_score():
    rows=[candle(100,101,99,100)]*20+[candle(100,101,98,100.6,300)]
    f=build_features(rows,[{"size":10,"side":"buy"}]*10,{"best_bid":100,"best_ask":101,"bid_depth_5":1200,"ask_depth_5":400})
    d=evaluate(f,side="LONG",entry=100,target=102); assert not d.allowed and "SPREAD_TOO_WIDE" in d.rejected
def test_independent_forecast_is_required():
    d=evaluate(feature_set(),side="LONG",entry=100,target=102); assert not d.allowed and "INDEPENDENT_FORECAST_REQUIRED" in d.rejected

def test_cost_buffer_is_hard_gate():
    d=evaluate(feature_set(),side="LONG",entry=100,target=102,forecast_edge_bps=1000,cfg=ScalpingGateConfig(min_move_to_cost=1000)); assert not d.allowed and "EXPECTED_MOVE_BELOW_COST_BUFFER" in d.rejected

def test_forecast_is_not_score_derived():
    d=evaluate(feature_set(),side="LONG",entry=100,target=102,forecast_edge_bps=40); assert d.expected_move_bps==40.0 and d.forecast_source=="independent_forecast"
def test_loss_halt_is_hard_gate():
    d=evaluate(feature_set(),side="LONG",entry=100,target=102,consecutive_losses=3); assert not d.allowed and "CONSECUTIVE_LOSS_HALT" in d.rejected
