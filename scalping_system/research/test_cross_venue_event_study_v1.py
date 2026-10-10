import unittest
from research.cross_venue_event_study_v1 import pct, summarize, return_bps, make_timeline, matched_baseline


class EventStudyTests(unittest.TestCase):
    def test_percentile_interpolates(self):
        self.assertAlmostEqual(pct([0, 10], 50), 5)

    def test_empty_summary_is_explicit(self):
        self.assertEqual(summarize([])["n"], 0)
        self.assertIsNone(summarize([])["mean_bps"])

    def test_log_return_bps(self):
        a = {"mid": 100.0}
        b = {"mid": 101.0}
        self.assertAlmostEqual(return_bps(a, b), 10000 * __import__("math").log(1.01))

    def test_timeline_ignores_non_quote_events(self):
        raw = [
            {"venue": "binance", "kind": "depthUpdate", "receive_mono_s": 1.0, "mid": 100},
            {"venue": "binance", "kind": "aggTrade", "receive_mono_s": 1.1, "mid": 101},
            {"venue": "delta", "kind": "ob_l1", "receive_mono_s": 1.2, "mid": 100},
        ]
        result = make_timeline(raw)
        self.assertEqual(len(result["binance"]), 1)
        self.assertEqual(len(result["delta"]), 1)

    def test_empty_baseline_is_safe(self):
        result = matched_baseline({"binance": [], "delta": []})
        self.assertEqual(result[5], [])
        self.assertEqual(result[30], [])


if __name__ == "__main__":
    unittest.main()
