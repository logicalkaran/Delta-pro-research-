import json
import time
from unittest import TestCase

from delta_collector import microstructure


class MicrostructureTests(TestCase):
    def setUp(self):
        microstructure.reset()
        self.base = int(time.time() * 1_000_000)

    def tearDown(self):
        microstructure.reset()

    def feed(self, message):
        microstructure.update(message)

    def test_buy_sell_delta_and_percent(self):
        self.feed({"type": "ob_l1", "bp": "100", "bs": "100", "ap": "101", "as": "100"})
        self.feed({"type": "trades", "p": "101", "s": 10, "r": "t", "t": self.base})
        self.feed({"type": "trades", "p": "100", "s": 4, "r": "m", "t": self.base + 100_000})
        state = json.loads(microstructure.OUT.read_text())
        w = state["windows"]["5"]
        self.assertEqual(w["buy_volume"], 10.0)
        self.assertEqual(w["sell_volume"], 4.0)
        self.assertEqual(w["delta"], 6.0)
        self.assertAlmostEqual(w["delta_pct"], 6 / 14, places=5)

    def test_l2_imbalance(self):
        self.feed({"type": "ob_l2", "b": [["100", "60"], ["99", "40"]], "a": [["101", "20"], ["102", "20"]]})
        state = json.loads(microstructure.OUT.read_text())
        book = state["order_book"]
        self.assertAlmostEqual(book["imbalance_5"], 60 / 140, places=5)

    def test_price_delta_divergence_absorption(self):
        self.feed({"type": "ob_l1", "bp": "100", "bs": "100", "ap": "101", "as": "300"})
        for i in range(10):
            self.feed({"type": "trades", "p": "101", "s": 10, "r": "t", "t": self.base + i * 100_000})
        state = json.loads(microstructure.OUT.read_text())
        self.assertEqual(state["regime"], "BUYER_ABSORPTION")

    def test_old_events_leave_short_window(self):
        self.feed({"type": "ob_l1", "bp": "100", "bs": "100", "ap": "101", "as": "100"})
        self.feed({"type": "trades", "p": "101", "s": 10, "r": "t", "t": self.base - 10_000_000})
        state = json.loads(microstructure.OUT.read_text())
        self.assertEqual(state["windows"]["5"]["trades"], 0)


if __name__ == "__main__":
    import unittest
    unittest.main()
