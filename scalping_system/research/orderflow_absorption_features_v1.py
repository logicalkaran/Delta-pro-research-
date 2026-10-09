"""Bounded, read-only order-flow features for absorption research.

CVD divergence and depth recovery are observable proxies, not proof of hidden
institutional/iceberg orders. This module has no network or execution code.
"""
from __future__ import annotations
from collections import deque
from dataclasses import dataclass, asdict
from math import isfinite
from typing import Optional


def _num(value, default=0.0):
    try:
        n = float(value)
        return n if isfinite(n) else default
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class OrderFlowFeatures:
    status: str
    cvd: float
    cvd_delta: float
    sell_volume: float
    buy_volume: float
    price_change_bps: float
    cvd_divergence: str
    bid_replenishment_ratio: Optional[float]
    ask_replenishment_ratio: Optional[float]
    bid_depth: float
    ask_depth: float
    book_age_seconds: Optional[float]
    trade_count: int
    book_count: int
    caveat: str = "DIVERGENCE_IS_NOT_PROOF_OF_ICEBERG_OR_CAUSATION"

    def to_dict(self):
        return asdict(self)


class OrderFlowAbsorptionTape:
    """Bounded in-memory tape; timestamps must be Unix seconds."""
    def __init__(self, max_trades=5000, max_books=1000, window_seconds=30.0,
                 max_book_age_seconds=2.0):
        if min(max_trades, max_books) < 2 or window_seconds <= 0 or max_book_age_seconds <= 0:
            raise ValueError("invalid buffer/window configuration")
        self.trades = deque(maxlen=int(max_trades))
        self.books = deque(maxlen=int(max_books))
        self.window_seconds = float(window_seconds)
        self.max_book_age_seconds = float(max_book_age_seconds)

    def add_trade(self, timestamp, price, size, aggressor_side):
        ts, px, qty = _num(timestamp, -1), _num(price), abs(_num(size))
        side = str(aggressor_side).lower()
        if ts < 0 or px <= 0 or qty <= 0 or side not in ("buy", "sell"):
            return False
        self.trades.append({"ts": ts, "price": px, "size": qty, "side": side,
                            "delta": qty if side == "buy" else -qty})
        return True

    def add_book(self, timestamp, mid_price, bid_depth, ask_depth):
        ts, mid = _num(timestamp, -1), _num(mid_price)
        bid, ask = _num(bid_depth, -1), _num(ask_depth, -1)
        if ts < 0 or mid <= 0 or bid < 0 or ask < 0:
            return False
        if self.books and ts < self.books[-1]["ts"]:
            return False
        self.books.append({"ts": ts, "mid": mid, "bid": bid, "ask": ask})
        return True

    @staticmethod
    def _recovery(rows, side):
        # Recovery from the minimum observed depth relative to pre-trough depth.
        # Require an actual trough and at least one later snapshot.
        if len(rows) < 3:
            return None
        vals = [r[side] for r in rows]
        trough = min(range(1, len(vals) - 1), key=lambda i: vals[i])
        baseline, low, current = vals[trough - 1], vals[trough], vals[-1]
        if baseline <= low:
            return None
        return round(max(0.0, (current - low) / (baseline - low)), 4)

    def features(self, now=None):
        now = _num(now, 0.0)
        if now <= 0:
            now = max(self.trades[-1]["ts"] if self.trades else 0,
                      self.books[-1]["ts"] if self.books else 0)
        cutoff = now - self.window_seconds
        trades = [t for t in self.trades if cutoff <= t["ts"] <= now]
        books = [b for b in self.books if cutoff <= b["ts"] <= now]
        buys = sum(t["size"] for t in trades if t["side"] == "buy")
        sells = sum(t["size"] for t in trades if t["side"] == "sell")
        cvd_delta = buys - sells
        cvd = sum(t["delta"] for t in self.trades if t["ts"] <= now)
        price_change_bps = 0.0
        if len(books) >= 2 and books[0]["mid"] > 0:
            price_change_bps = (books[-1]["mid"] / books[0]["mid"] - 1.0) * 10000
        total = buys + sells
        sell_pressure = total > 0 and cvd_delta / total <= -0.20
        buy_pressure = total > 0 and cvd_delta / total >= 0.20
        if sell_pressure and price_change_bps >= -0.5:
            divergence = "POSSIBLE_BUYER_ABSORPTION"
        elif buy_pressure and price_change_bps <= 0.5:
            divergence = "POSSIBLE_SELLER_ABSORPTION"
        else:
            divergence = "NONE"
        age = max(0.0, now - self.books[-1]["ts"]) if self.books else None
        fresh = age is not None and age <= self.max_book_age_seconds
        status = "OK" if fresh and trades and books else "INSUFFICIENT_OR_STALE_DATA"
        return OrderFlowFeatures(
            status=status, cvd=round(cvd, 8), cvd_delta=round(cvd_delta, 8),
            sell_volume=round(sells, 8), buy_volume=round(buys, 8),
            price_change_bps=round(price_change_bps, 5), cvd_divergence=divergence,
            bid_replenishment_ratio=self._recovery(books, "bid"),
            ask_replenishment_ratio=self._recovery(books, "ask"),
            bid_depth=books[-1]["bid"] if books else 0.0,
            ask_depth=books[-1]["ask"] if books else 0.0,
            book_age_seconds=round(age, 4) if age is not None else None,
            trade_count=len(trades), book_count=len(books))
