import zlib


class DeltaOrderBook:
    def __init__(self):
        self.asks = {}
        self.bids = {}
        self.last_seq = None

    @staticmethod
    def _price(value):
        return str(value)

    @staticmethod
    def _size(value):
        return int(value)

    def load_snapshot(self, message):
        if message.get("action") != "snapshot":
            raise ValueError("Expected snapshot message")

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

        self.last_seq = int(message["seq"])

    def apply_update(self, message):
        if message.get("action") != "update":
            raise ValueError("Expected update message")

        seq = int(message["seq"])

        if self.last_seq is None:
            raise RuntimeError("Order book has no snapshot")

        expected = self.last_seq + 1

        if seq != expected:
            raise RuntimeError(
                f"SEQUENCE GAP: expected={expected}, received={seq}"
            )

        # ASK updates
        for price, size in message.get("a", []):
            price = self._price(price)
            size = self._size(size)

            if size == 0:
                self.asks.pop(price, None)
            else:
                self.asks[price] = size

        # BID updates
        for price, size in message.get("b", []):
            price = self._price(price)
            size = self._size(size)

            if size == 0:
                self.bids.pop(price, None)
            else:
                self.bids[price] = size

        self.last_seq = seq

    def checksum_string(self):
        # Delta:
        # asks ascending
        # bids descending
        # first 10 levels only

        asks = sorted(
            self.asks.items(),
            key=lambda x: float(x[0])
        )[:10]

        bids = sorted(
            self.bids.items(),
            key=lambda x: float(x[0]),
            reverse=True
        )[:10]

        asks_string = ",".join(
            f"{price}:{size}"
            for price, size in asks
        )

        bids_string = ",".join(
            f"{price}:{size}"
            for price, size in bids
        )

        return asks_string + "|" + bids_string

    def checksum(self):
        checksum_string = self.checksum_string()

        return zlib.crc32(
            checksum_string.encode("utf-8")
        ) & 0xffffffff

    def verify_checksum(self, expected):
        return self.checksum() == int(expected)

    def best_bid(self):
        if not self.bids:
            return None

        return max(
            self.bids.keys(),
            key=float
        )

    def best_ask(self):
        if not self.asks:
            return None

        return min(
            self.asks.keys(),
            key=float
        )

    def spread(self):
        bid = self.best_bid()
        ask = self.best_ask()

        if bid is None or ask is None:
            return None

        return float(ask) - float(bid)

    def stats(self):
        return {
            "sequence": self.last_seq,
            "ask_levels": len(self.asks),
            "bid_levels": len(self.bids),
            "best_bid": self.best_bid(),
            "best_ask": self.best_ask(),
            "spread": self.spread(),
        }
