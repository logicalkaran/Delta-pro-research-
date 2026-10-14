from paper.professional_paper_v1 import signal
s={"timestamp":1791576000,"windows":{"5":{"trades":10,"buy_volume":80,"sell_volume":20,"delta_pct":.6},"30":{"delta_pct":.3},"60":{"delta_pct":.2}},"price":{"5":{"return_pct":.1}},"order_book":{"mid_price":84000,"spread":.5,"imbalance_5":.5},"quality":{"fresh_seconds":.1}}
a,sc,r=signal(s,{"edge_v42":{"state":"VENUE_CONFIRMATION"}})
assert a=="NO_TRADE"
b,_,_=signal(s,{"edge_v42":{"state":"DIVERGENCE"}})
assert b=="NO_TRADE"
print("PROFESSIONAL PAPER V1 TEST: PASS")
