"""V4.2 cross-venue edge classifier.

Research-only. No orders. Converts normalized venue snapshots into
confirmation/divergence features for the professional edge engine.
"""
from dataclasses import dataclass
from strategy.cross_venue_v41 import VenueSnapshot, compare

@dataclass(frozen=True)
class V42Config:
    confirmation_bps: float = 0.75
    divergence_bps: float = 2.0

def classify(snapshots, cfg=V42Config()):
    c=compare(snapshots)
    if not c["valid"]:
        return {"state":"NO_DATA","edge":0.0,**c}
    rows=c["venues"]
    if len(rows)<2:
        return {"state":"SINGLE_VENUE","edge":0.0,**c}
    mx=max(rows,key=lambda x:x["premium_bps"])
    mn=min(rows,key=lambda x:x["premium_bps"])
    spread=mx["premium_bps"]-mn["premium_bps"]
    if spread >= cfg.divergence_bps:
        state="DIVERGENCE"
        edge=-min(1.0,spread/10.0)
    elif max(abs(x["premium_bps"]) for x in rows) <= cfg.confirmation_bps:
        state="VENUE_CONFIRMATION"
        edge=1.0
    else:
        state="MILD_DIVERGENCE"
        edge=0.25
    return {"state":state,"edge":edge,"reference_price":c["reference_price"],
            "spread_bps":spread,"leader":mx["venue"],"lagger":mn["venue"],
            "max_premium_bps":c["max_premium_bps"],
            "min_premium_bps":c["min_premium_bps"],"venues":rows}
