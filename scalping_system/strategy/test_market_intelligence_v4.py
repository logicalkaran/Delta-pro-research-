from strategy.market_intelligence_v4 import features, score

state = {
 "timestamp": 1791359333,
 "windows":{"5":{"trades":5,"buy_volume":10,"sell_volume":2,"delta_pct":.667},"30":{"trades":30,"buy_volume":30,"sell_volume":10,"delta_pct":.50},"60":{"trades":60,"buy_volume":50,"sell_volume":20,"delta_pct":.43}},
 "price":{"5":{"return_pct":.10}},
 "order_book":{"mid_price":84000,"spread":.5,"bid_depth_5":10000,"ask_depth_5":5000,"imbalance_5":.333},
 "quality":{"fresh_seconds":.1}
}
f=features(state)
assert "flow_acceleration" in f
assert score(f)["action"] in {"LONG","SHORT","NO_TRADE"}
print("V4 FEATURE TEST: PASS")
