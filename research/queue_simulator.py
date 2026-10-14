"""Deterministic passive queue model. Never sends or cancels real orders."""
from __future__ import annotations
from dataclasses import dataclass
import math

@dataclass(frozen=True)
class QueueResult:
    status: str
    filled: bool
    fill_ts: float | None
    initial_queue: float
    remaining_queue: float
    cumulative_aggressive_volume: float
    reason: str

class PassiveQueue:
    def __init__(self, *, side: str, queue_ahead: float, limit_price: float, placed_ts: float,
                 displayed_queue_volume: float | None = None):
        if side not in {"buy", "sell"}: raise ValueError("side must be buy or sell")
        vals = [queue_ahead, limit_price, placed_ts]
        if displayed_queue_volume is not None: vals.append(displayed_queue_volume)
        if any(not math.isfinite(float(v)) for v in vals) or queue_ahead < 0 or limit_price <= 0 or placed_ts <= 0:
            raise ValueError("invalid initial queue inputs")
        if displayed_queue_volume is not None and displayed_queue_volume < queue_ahead:
            raise ValueError("displayed queue volume cannot be less than volume ahead")
        self.side, self.initial_queue = side, float(queue_ahead)
        self.remaining_queue, self.limit_price, self.placed_ts = float(queue_ahead), float(limit_price), float(placed_ts)
        self.displayed_queue_volume = float(displayed_queue_volume) if displayed_queue_volume is not None else None
        self.aggressive_volume = 0.0
        self.fill_ts = None
        self.last_ts = float(placed_ts)
        self.status = "RESTING"

    def on_event(self, *, event_ts: float, aggressive_buy_volume: float = 0.0,
                 aggressive_sell_volume: float = 0.0, displayed_queue_volume: float | None = None,
                 same_price: bool = True) -> QueueResult:
        if self.status != "RESTING": raise ValueError("queue is no longer resting")
        vals = [event_ts, aggressive_buy_volume, aggressive_sell_volume]
        if displayed_queue_volume is not None: vals.append(displayed_queue_volume)
        if any(not math.isfinite(float(v)) for v in vals) or event_ts <= self.last_ts or min(aggressive_buy_volume, aggressive_sell_volume) < 0:
            raise ValueError("invalid or non-monotonic queue event")
        if displayed_queue_volume is not None and displayed_queue_volume < 0: raise ValueError("negative displayed queue")
        self.last_ts = float(event_ts)
        if displayed_queue_volume is not None and same_price:
            if self.displayed_queue_volume is not None and self.displayed_queue_volume > 0:
                delta = float(displayed_queue_volume) - self.displayed_queue_volume
                # Proportional thinning allocates observed cancellations/additions to the queue ahead.
                self.remaining_queue = max(0.0, self.remaining_queue + delta * self.remaining_queue / self.displayed_queue_volume)
            self.displayed_queue_volume = float(displayed_queue_volume)
        # Passive buy fills on aggressive sells; passive sell fills on aggressive buys.
        traded = float(aggressive_sell_volume if self.side == "buy" else aggressive_buy_volume)
        self.aggressive_volume += traded
        if traded > 0 and traded >= self.remaining_queue:
            self.remaining_queue = 0.0
            self.fill_ts, self.status = float(event_ts), "FILLED"
            return self.result("FIRST_PASSAGE_AGGRESSIVE_VOLUME")
        self.remaining_queue = max(0.0, self.remaining_queue-traded)
        return self.result("QUEUE_NOT_CONSUMED")

    def expire(self, *, now_ts: float) -> QueueResult:
        if not math.isfinite(now_ts) or now_ts < self.last_ts: raise ValueError("invalid expiry timestamp")
        if self.status == "RESTING": self.status = "CANCELED"
        return self.result("TWAP_INTERVAL_EXPIRED" if self.status == "CANCELED" else "ALREADY_TERMINAL")

    def result(self, reason: str) -> QueueResult:
        return QueueResult(self.status, self.status == "FILLED", self.fill_ts,
                           self.initial_queue, self.remaining_queue, self.aggressive_volume, reason)
