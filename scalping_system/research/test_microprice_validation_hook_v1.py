import unittest
from research.microprice_validation_hook_v1 import microprice_features, make_row


class MicropriceTests(unittest.TestCase):
    def test_equal_depth_means_mid(self):
        ob = {"bids": [[100, 10], [99, 10]], "asks": [[102, 10], [103, 10]]}
        f = microprice_features(ob)
        self.assertEqual(f["status"], "OK")
        self.assertAlmostEqual(f["microprice"], f["mid"])
        self.assertEqual(f["direction"], 0)

    def test_bid_imbalance_shifts_up(self):
        ob = {"bids": [[100, 1000], [99, 500]], "asks": [[102, 10], [103, 10]]}
        f = microprice_features(ob)
        self.assertGreater(f["microprice"], f["mid"])
        self.assertEqual(f["direction"], 1)
        self.assertTrue(f["entry_threshold_pass"])

    def test_missing_level_arrays_abstain(self):
        f = microprice_features({"best_bid": 100, "best_ask": 102, "bid_depth_5": 999})
        self.assertEqual(f["status"], "MISSING_L2_LEVELS")
        self.assertFalse(f["entry_threshold_pass"])

    def test_crossed_book_abstains(self):
        f = microprice_features({"bids": [[103, 10]], "asks": [[102, 10]]})
        self.assertEqual(f["status"], "INVALID_OR_CROSSED_BOOK")
        self.assertFalse(f["entry_threshold_pass"])

    def test_row_is_research_only_and_detects_aggregate_only_state(self):
        r = make_row({"updated_at_epoch": 100.0, "order_book": {"best_bid": 100, "best_ask": 102}}, now=100.1)
        self.assertTrue(r["research_only"])
        self.assertFalse(r["real_orders"])
        self.assertEqual(r["status"], "MISSING_L2_LEVELS")


if __name__ == "__main__":
    unittest.main()


def test_single_level_book_uses_spread_as_tick_fallback():
    f = microprice_features({"bids": [[100, 5]], "asks": [[101, 2]]})
    assert f["status"] == "OK"
    assert f["inferred_tick_size"] == 1.0
