import json
import zlib


class OrderBookEngine:
    """
    Canonical Delta Exchange order-book reconstruction engine.

    Handles:
      - snapshot
      - incremental updates
      - best bid / ask
      - mid price
      - spread
      - L1 imbalance
      - L5 imbalance
      - checksum
      - sequence tracking
    """

    def __init__(self):
        self.asks = {}
        self.bids = {}

        self.last_seq = None
        self.last_ts = None

        self.snapshot_seen = False
        self.update_count = 0

    @staticmethod
    def _apply_side(book, updates):
        for price, size in updates:

            size = int(size)

            if size == 0:
                book.pop(price, None)
            else:
                book[price] = size

    def apply_snapshot(self, message):
        self.asks.clear()
        self.bids.clear()

        self._apply_side(
            self.asks,
            message.get("a", [])
        )

        self._apply_side(
            self.bids,
            message.get("b", [])
        )

        self.snapshot_seen = True
        self.last_seq = message.get("seq")
        self.last_ts = message.get("ts")

        return self.state()

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
            message.get("a", [])
        )

        self._apply_side(
            self.bids,
            message.get("b", [])
        )

        self.last_seq = seq
        self.last_ts = message.get("ts")
        self.update_count += 1

        return self.state()

    def best_bid(self):
        if not self.bids:
            return None

        price = max(
            self.bids,
            key=float
        )

        return float(price), self.bids[price]

    def best_ask(self):
        if not self.asks:
            return None

        price = min(
            self.asks,
            key=float
        )

        return float(price), self.asks[price]

    def mid_price(self):
        bid = self.best_bid()
        ask = self.best_ask()

        if bid is None or ask is None:
            return None

        return (bid[0] + ask[0]) / 2.0

    def spread(self):
        bid = self.best_bid()
        ask = self.best_ask()

        if bid is None or ask is None:
            return None

        return ask[0] - bid[0]

    def l1_imbalance(self):
        bid = self.best_bid()
        ask = self.best_ask()

        if bid is None or ask is None:
            return None

        bid_size = bid[1]
        ask_size = ask[1]

        denominator = bid_size + ask_size

        if denominator <= 0:
            return None

        return (
            (bid_size - ask_size)
            / denominator
        )

    def top_levels(self, depth=5):
        asks = sorted(
            self.asks.items(),
            key=lambda x: float(x[0])
        )[:depth]

        bids = sorted(
            self.bids.items(),
            key=lambda x: float(x[0]),
            reverse=True
        )[:depth]

        return bids, asks

    def l5_imbalance(self):
        bids, asks = self.top_levels(5)

        if len(bids) < 5 or len(asks) < 5:
            return None

        bid_size = sum(
            int(size)
            for _, size in bids
        )

        ask_size = sum(
            int(size)
            for _, size in asks
        )

        denominator = bid_size + ask_size

        if denominator <= 0:
            return None

        return (
            (bid_size - ask_size)
            / denominator
        )

    def checksum(self, depth=10):
        bids, asks = self.top_levels(depth)

        bid_text = ",".join(
            f"{price}:{size}"
            for price, size in bids
        )

        ask_text = ",".join(
            f"{price}:{size}"
            for price, size in asks
        )

        payload = (
            ask_text
            + "|"
            + bid_text
        )

        return zlib.crc32(
            payload.encode()
        )

    def state(self):
        bid = self.best_bid()
        ask = self.best_ask()

        return {
            "seq": self.last_seq,
            "ts": self.last_ts,
            "bid": bid[0] if bid else None,
            "bid_size": bid[1] if bid else None,
            "ask": ask[0] if ask else None,
            "ask_size": ask[1] if ask else None,
            "mid": self.mid_price(),
            "spread": self.spread(),
            "l1_imbalance": self.l1_imbalance(),
            "l5_imbalance": self.l5_imbalance(),
            "bid_levels": len(self.bids),
            "ask_levels": len(self.asks),
        }


def process_message(engine, message):
    action = message.get("action")

    if action == "snapshot":
        return engine.apply_snapshot(message)

    if action == "update":
        return engine.apply_update(message)

    return None
