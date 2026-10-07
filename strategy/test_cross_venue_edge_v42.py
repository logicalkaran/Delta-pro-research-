from strategy.cross_venue_edge_v42 import classify
from strategy.cross_venue_v41 import VenueSnapshot

a=classify([VenueSnapshot("a",84000),VenueSnapshot("b",84002)])
assert a["state"] in {"VENUE_CONFIRMATION","MILD_DIVERGENCE","DIVERGENCE"}
b=classify([VenueSnapshot("a",84000),VenueSnapshot("b",84200)])
assert b["state"] == "DIVERGENCE"
print("CROSS-VENUE V4.2 TEST: PASS")
