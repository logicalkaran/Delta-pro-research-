import zlib


class DeltaOrderBook:
    def __init__(self):
        self.asks = {}
        self.bids = {}
        self.last_seq = None

    @staticmethod
    def _price(value):
        return float(value)

    @staticmethod
    def _size(value):
        return int(value)

    def load_snapshot(self, message):
        self.asks.clear()
        self.bids.clear()

        for price, size in message.get("a", []):
            size = self._size(size)
            if size > 0:
                self.asks[self._price(price)] = size

        for price, size in message.get("b", []):
            size = self._size(size)
            if size > 0:
                self.bids[self._price(price)] = size

        self.last_seq = message["seq"]

    def apply_update(self, message):
        seq = message["seq"]

        if self.last_seq is None:
            raise RuntimeError("Order book has no snapshot")

        expected = self.last_seq + 1

        if seq != expected:
            raise RuntimeError(
                f"SEQUENCE GAP: expected={expected}, received={seq}"
            )

        for price, size in message.get("a", []):
            price = self._price(price)
            size = self._size(size)

            if size == 0:
                self.asks.pop(price, None)
            else:
                self.asks[price] = size

        for price, size in message.get("b", []):
            price = self._price(price)
            size = self._size(size)

            if size == 0:
                self.bids.pop(price, None)
            else:
                self.bids[price] = size

        self.last_seq = seq

    def checksum_string(self):
        asks = sorted(self.asks.items())[:10]
        bids = sorted(
            self.bids.items(),
            key=lambda x: x[0],
            reverse=True,
        )[:10]

        ask_string = ",".join(
            f"{price:g}:{size}"
            for price, size in asks
        )

        bid_string = ",".join(
            f"{price:g}:{size}"
            for price, size in bids
        )

        return ask_string + "|" + bid_string

    def checksum(self):
        data = self.checksum_string().encode("utf-8")
        return zlib.crc32(data) & 0xffffffff

    def verify_checksum(self, expected):
        actual = self.checksum()
        return actual == int(expected)

    def best_bid(self):
        return max(self.bids) if self.bids else None

    def best_ask(self):
        return min(self.asks) if self.asks else None

    def spread(self):
        bid = self.best_bid()
        ask = self.best_ask()

        if bid is None or ask is None:
            return None

        return ask - bid

    def stats(self):
        return {
            "sequence": self.last_seq,
            "ask_levels": len(self.asks),
            "bid_levels": len(self.bids),
            "best_bid": self.best_bid(),
            "best_ask": self.best_ask(),
            "spread": self.spread(),
        }
