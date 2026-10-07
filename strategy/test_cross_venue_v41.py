from strategy.cross_venue_v41 import VenueSnapshot, compare

r=compare([
 VenueSnapshot("delta",84000,83999.5,84000.0,1000),
 VenueSnapshot("reference",84010,84009.5,84010.0,2000),
])
assert r["valid"]
assert len(r["venues"]) == 2
assert r["max_premium_bps"] > 0
print("CROSS-VENUE V4.1 TEST: PASS")
