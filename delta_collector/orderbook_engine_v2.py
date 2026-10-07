from __future__ import annotations


class OrderBookEngine:
    """
    Fast reference OrderBookEngine V2.1.

    V1 remains the correctness oracle.

    Design:
      - prices normalized to numeric values
      - sizes normalized to integers
      - zero size removes a level
      - cached best bid/ask
      - top-5 calculated once per state
      - no repeated best-price scans inside state()
      - same external state schema as V1
    """

    def __init__(self):
        self.asks = {}
        self.bids = {}

        self.last_seq = None
        self.last_ts = None

        self.snapshot_seen = False
        self.update_count = 0

        self._best_bid_price = None
        self._best_bid_size = None
        self._best_ask_price = None
        self._best_ask_size = None

    @staticmethod
    def _normalize_price(price):
        return float(price)

    @staticmethod
    def _normalize_size(size):
        return int(size)

    @classmethod
    def _apply_side(cls, book, updates):
        changed = []

        for price, size in updates:
            price = cls._normalize_price(price)
            size = cls._normalize_size(size)

            if size == 0:
                book.pop(price, None)
            else:
                book[price] = size

            changed.append(price)

        return changed

    def _refresh_best(self):
        if self.bids:
            price = max(self.bids)
            self._best_bid_price = price
            self._best_bid_size = self.bids[price]
        else:
            self._best_bid_price = None
            self._best_bid_size = None

        if self.asks:
            price = min(self.asks)
            self._best_ask_price = price
            self._best_ask_size = self.asks[price]
        else:
            self._best_ask_price = None
            self._best_ask_size = None

    def _top_levels(self, depth=5):
        bids = sorted(
            self.bids.items(),
            key=lambda x: x[0],
            reverse=True,
        )[:depth]

        asks = sorted(
            self.asks.items(),
            key=lambda x: x[0],
        )[:depth]

        return bids, asks

    def _build_state(self):
        bid = self._best_bid_price
        ask = self._best_ask_price

        bid_size = self._best_bid_size
        ask_size = self._best_ask_size

        if bid is None or ask is None:
            mid = None
            spread = None
            l1 = None
        else:
            mid = (bid + ask) / 2.0
            spread = ask - bid

            denominator = bid_size + ask_size

            if denominator > 0:
                l1 = (
                    (bid_size - ask_size)
                    / denominator
                )
            else:
                l1 = None

        bids, asks = self._top_levels(5)

        if len(bids) < 5 or len(asks) < 5:
            l5 = None
        else:
            bid_total = sum(
                size for _, size in bids
            )

            ask_total = sum(
                size for _, size in asks
            )

            denominator = bid_total + ask_total

            if denominator > 0:
                l5 = (
                    (bid_total - ask_total)
                    / denominator
                )
            else:
                l5 = None

        return {
            "seq": self.last_seq,
            "ts": self.last_ts,

            "bid": bid,
            "bid_size": bid_size,

            "ask": ask,
            "ask_size": ask_size,

            "mid": mid,
            "spread": spread,

            "l1_imbalance": l1,
            "l5_imbalance": l5,

            "bid_levels": len(self.bids),
            "ask_levels": len(self.asks),
        }

    def apply_snapshot(self, message):
        self.asks.clear()
        self.bids.clear()

        self._apply_side(
            self.asks,
            message.get("a", []),
        )

        self._apply_side(
            self.bids,
            message.get("b", []),
        )

        self.snapshot_seen = True
        self.last_seq = message.get("seq")
        self.last_ts = message.get("ts")

        self._refresh_best()

        return self._build_state()

    def apply_update(self, message):
        if not self.snapshot_seen:
            raise RuntimeError(
                "Cannot apply update before snapshot"
            )

        seq = message.get("seq")

        if self.last_seq is not None:
            expected = self.last_seq + 1

            if seq != expected:
                raise RuntimeError(
                    f"Sequence error: "
                    f"expected {expected}, got {seq}"
                )

        self._apply_side(
            self.asks,
            message.get("a", []),
        )

        self._apply_side(
            self.bids,
            message.get("b", []),
        )

        self.last_seq = seq
        self.last_ts = message.get("ts")
        self.update_count += 1

        self._refresh_best()

        return self._build_state()


def process_message(engine, message):
    action = message.get("action")

    if action == "snapshot":
        return engine.apply_snapshot(message)

    if action == "update":
        return engine.apply_update(message)

    return None
