import unittest
from research.microprice_ic_markout_benchmark_v1 import corr, rank, approx_p_two_sided, benchmark, hac_spearman_t, quintile_profile


class ICTests(unittest.TestCase):
    def test_tie_aware_rank(self):
        self.assertEqual(rank([1, 1, 3]), [1.5, 1.5, 3.0])

    def test_spearman_perfect_monotonic(self):
        self.assertAlmostEqual(corr([1, 2, 3, 4], [10, 20, 30, 40]), 1.0)

    def test_p_value_guard(self):
        self.assertIsNone(approx_p_two_sided(None, 10))
        self.assertEqual(approx_p_two_sided(1.0, 10), 0.0)

    def test_hac_rank_statistic_returns_lag_and_finite_t(self):
        x=list(range(1, 21))
        y=[v + ((i % 4) - 1.5) * 1.7 for i, v in enumerate(x)]
        t, p, lags=hac_spearman_t(x, y)
        self.assertIsNotNone(t)
        self.assertIsNotNone(p)
        self.assertGreaterEqual(lags, 0)

    def test_quintile_profile_requires_monotonic_means(self):
        rows=[{"microprice_imbalance_n":float(i), "target_15s_bps":float(i//5)} for i in range(25)]
        result=quintile_profile(rows)
        self.assertTrue(result["eligible"])
        self.assertTrue(result["strictly_monotonic_increasing"])
        self.assertEqual(len(result["quintiles"]), 5)

    def test_session_boundaries_and_empty_data(self):
        r = benchmark([])
        self.assertEqual(r["labeled_15s_rows"], 0)
        self.assertFalse(r["real_orders"])
        rows = [
            {"ts": 1, "mid": 100, "session_id": "a", "microprice_method": "price_distance_decay_v1", "microprice_imbalance_n": 0.1, "l1_imbalance": 0.2, "signed_flow_1s": 1},
            {"ts": 16, "mid": 101, "session_id": "a", "microprice_method": "price_distance_decay_v1", "microprice_imbalance_n": 0.2, "l1_imbalance": 0.3, "signed_flow_1s": 2},
            {"ts": 17, "mid": 90, "session_id": "b", "microprice_method": "price_distance_decay_v1", "microprice_imbalance_n": 0.3, "l1_imbalance": 0.4, "signed_flow_1s": 3},
        ]
        r = benchmark(rows)
        self.assertEqual(r["labeled_15s_rows"], 1)
        self.assertEqual(r["session_count"], 2)
        self.assertEqual(r["holdout_session_id"], "b")
        self.assertEqual(r["holdout_labeled_15s_rows"], 0)


if __name__ == "__main__":
    unittest.main()


def test_ic_feature_set_includes_depth_derivatives_and_cross_venue_schema(tmp_path):
    from research.microprice_ic_markout_benchmark_v1 import FEATURES, load
    path = tmp_path / "cross.jsonl"
    path.write_text('{"schema":"cross_venue_depth_toxicity_v1","session_id":"s","ts":1,"mid":100,"delta_imbalance_5":0.2,"binance_minus_delta_imbalance":0.5}\n')
    rows = load(path)
    assert len(rows) == 1
    assert "delta_bid_replenishment_rate_200ms" in FEATURES
    assert "binance_imbalance_5" in FEATURES
    assert "vpin" in FEATURES
