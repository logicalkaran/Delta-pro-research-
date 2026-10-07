"""Read-only cross-venue normalizer for BTC research.

Consumes public quote/derivatives snapshots supplied by adapters. No credentials
and no order submission are handled here.
"""
from dataclasses import dataclass

@dataclass(frozen=True)
class VenueSnapshot:
    venue: str
    price: float
    bid: float = 0.0
    ask: float = 0.0
    volume: float = 0.0
    open_interest: float = 0.0
    funding: float = 0.0

def _f(x,d=0.0):
    try: return float(x)
    except (TypeError,ValueError): return d

def normalize(s):
    bid=_f(s.bid); ask=_f(s.ask); price=_f(s.price)
    return {"venue":s.venue,"price":price,"bid":bid,"ask":ask,
            "spread":max(0,ask-bid) if ask and bid else 0,
            "volume":_f(s.volume),"open_interest":_f(s.open_interest),
            "funding":_f(s.funding)}

def compare(snapshots):
    rows=[normalize(s) for s in snapshots if _f(s.price)>0]
    if not rows:
        return {"valid":False,"reason":"NO_VENUE_DATA"}
    prices=[r["price"] for r in rows]
    ref=sum(prices)/len(prices)
    out=[]
    for r in rows:
        out.append({**r,"premium_bps":(r["price"]/ref-1)*10000})
    return {"valid":True,"reference_price":ref,"venues":out,
            "max_premium_bps":max(x["premium_bps"] for x in out),
            "min_premium_bps":min(x["premium_bps"] for x in out)}
