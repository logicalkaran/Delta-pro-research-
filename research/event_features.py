"""Event-time L5 MLOFI features. Research-only; no exchange/order interfaces."""
from __future__ import annotations
from dataclasses import dataclass
import math
from typing import Sequence

Level = tuple[float, float]

def _levels(values: Sequence[Sequence[float]], name: str) -> tuple[Level, ...]:
    if len(values) < 5:
        raise ValueError(f"{name} requires five book levels")
    out = []
    for row in values[:5]:
        if len(row) < 2:
            raise ValueError("each level requires price and quantity")
        p, q = float(row[0]), float(row[1])
        if not math.isfinite(p) or not math.isfinite(q) or p <= 0 or q < 0:
            raise ValueError("invalid book level")
        out.append((p, q))
    return tuple(out)

@dataclass(frozen=True)
class BookEvent:
    event_ts: float
    bids: tuple[Level, ...]
    asks: tuple[Level, ...]

    @classmethod
    def from_levels(cls, event_ts: float, bids, asks) -> "BookEvent":
        ts = float(event_ts)
        if not math.isfinite(ts) or ts <= 0:
            raise ValueError("exchange event timestamp must be finite and positive")
        b, a = _levels(bids, "bids"), _levels(asks, "asks")
        if b[0][0] >= a[0][0]:
            raise ValueError("book must be uncrossed")
        if any(b[i][0] < b[i+1][0] for i in range(4)):
            raise ValueError("bid levels must be descending")
        if any(a[i][0] > a[i+1][0] for i in range(4)):
            raise ValueError("ask levels must be ascending")
        return cls(ts, b, a)

def _level_flow(prev: tuple[Level, ...], cur: tuple[Level, ...], side: str) -> list[float]:
    flows = []
    for (p0, q0), (p1, q1) in zip(prev, cur):
        if side == "bid":
            f = q1 if p1 > p0 else q1 - q0 if p1 == p0 else -q0
        else:
            f = -q1 if p1 < p0 else q0 - q1 if p1 == p0 else q0
        flows.append(f)
    return flows

def mlofi(prev: BookEvent, cur: BookEvent, *, decay: float = 0.5) -> dict:
    """Compute exponentially weighted bid/ask OFI on a genuine state mutation."""
    if not math.isfinite(decay) or decay < 0:
        raise ValueError("decay must be finite and non-negative")
    if cur.event_ts <= prev.event_ts:
        raise ValueError("event timestamps must strictly increase")
    if cur.bids == prev.bids and cur.asks == prev.asks:
        raise ValueError("unchanged book is not an event-time observation")
    bid = _level_flow(prev.bids, cur.bids, "bid")
    ask = _level_flow(prev.asks, cur.asks, "ask")
    weights = [math.exp(-decay * i) for i in range(5)]
    b, a = sum(w*x for w,x in zip(weights,bid)), sum(w*x for w,x in zip(weights,ask))
    return {"event_ts": cur.event_ts, "elapsed_event_seconds": cur.event_ts-prev.event_ts,
            "bid_ofi_levels": bid, "ask_ofi_levels": ask, "weights": weights,
            "mlofi_bid": b, "mlofi_ask": a, "mlofi": b+a,
            "clock_kind": "exchange_event_time", "changed": True}
