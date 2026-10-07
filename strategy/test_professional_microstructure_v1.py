from strategy.professional_microstructure_v1 import professional_features, professional_decision

f={"spread_bps":1.0,"bid_depth_5":50000,"ask_depth_5":30000,"aggression_pressure":0.4,"depth_skew":0.2,"delta5":0.2,"delta30":0.1,"book_imbalance":0.2,"momentum_5":0.05}
p=professional_features(f)
assert 0 <= p["liquidity_stress"] <= 1
assert 0 <= p["adverse_selection"] <= 1
assert professional_decision(f)["action"] in {"LONG","SHORT","NO_TRADE"}
print("PROFESSIONAL MICROSTRUCTURE TEST: PASS")
