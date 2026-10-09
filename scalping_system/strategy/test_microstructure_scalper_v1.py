import unittest

from strategy.microstructure_scalper_v1 import evaluate


def state(delta=0.0, delta30=0.0, obi=0.0, obi10=0.0, ret5=0.0,
          trades=10, fresh=0.5, spread=0.5, mid=100_000.0):
    return {
        "regime": "TEST",
        "windows": {
            "5": {"delta_pct": delta, "delta": 10.0, "trades": trades},
            "30": {"delta_pct": delta30, "delta": 20.0, "trades": trades * 3},
        },
        "price": {"5": {"return_pct": ret5}},
        "order_book": {
            "mid_price": mid,
            "spread": spread,
            "imbalance_5": obi,
            "imbalance_10": obi10,
        },
        "quality": {"fresh_seconds": fresh},
    }


class MicrostructureScalperTests(unittest.TestCase):
    def test_long_alignment(self):
        s = evaluate(state(delta=0.30, delta30=0.15, obi=0.30, obi10=0.20, ret5=0.08))
        self.assertEqual(s.action, "LONG")
        self.assertGreaterEqual(s.score, 6)

    def test_short_alignment(self):
        s = evaluate(state(delta=-0.30, delta30=-0.15, obi=-0.30, obi10=-0.20, ret5=-0.08))
        self.assertEqual(s.action, "SHORT")
        self.assertLessEqual(s.score, -6)

    def test_conflict_stays_out(self):
        s = evaluate(state(delta=0.30, delta30=0.10, obi=-0.30, obi10=-0.20, ret5=-0.08))
        self.assertEqual(s.action, "NO_TRADE")

    def test_stale_data_blocks(self):
        s = evaluate(state(delta=0.50, delta30=0.30, obi=0.50, obi10=0.30, ret5=0.20, fresh=3.0))
        self.assertEqual(s.action, "NO_TRADE")
        self.assertIn("STALE_MICROSTRUCTURE", s.blocked)

    def test_wide_spread_blocks(self):
        s = evaluate(state(delta=0.50, delta30=0.30, obi=0.50, obi10=0.30, ret5=0.20, spread=100.0))
        self.assertEqual(s.action, "NO_TRADE")
        self.assertIn("WIDE_SPREAD", s.blocked)

    def test_low_sample_blocks(self):
        s = evaluate(state(delta=0.50, delta30=0.30, obi=0.50, obi10=0.30, ret5=0.20, trades=2))
        self.assertEqual(s.action, "NO_TRADE")
        self.assertIn("LOW_TRADE_SAMPLE", s.blocked)


if __name__ == "__main__":
    unittest.main()
