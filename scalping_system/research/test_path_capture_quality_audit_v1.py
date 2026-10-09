import unittest

from research.path_capture_quality_audit_v1 import gap_stats, timestamp_audit, classify_timestamp_sources


class PathCaptureQualityAuditTests(unittest.TestCase):
    def test_gap_quantiles_and_threshold_counts(self):
        result = gap_stats([0, 1, 2, 4, 10])
        self.assertEqual(result["median_seconds"], 1.5)
        self.assertAlmostEqual(result["p90_seconds"], 4.8)
        self.assertAlmostEqual(result["p95_seconds"], 5.4)
        self.assertAlmostEqual(result["p99_seconds"], 5.88)
        self.assertEqual(result["max_seconds"], 6)
        self.assertEqual(result["over_1_second"], 2)
        self.assertEqual(result["over_2_seconds"], 1)
        self.assertEqual(result["over_5_seconds"], 1)

    def test_duplicate_out_of_order_and_invalid_mid_audit(self):
        rows = [
            {"ts": 2, "mid": 100},
            {"ts": 1, "mid": 0},
            {"ts": 1, "mid": "nan"},
            {"ts": "bad", "mid": -2},
        ]
        result = timestamp_audit(rows, price_key="mid")
        self.assertEqual(result["duplicate_timestamp_rows"], 1)
        self.assertEqual(result["out_of_order_adjacent_pairs"], 1)
        self.assertEqual(result["invalid_or_missing_timestamp_rows"], 1)
        self.assertEqual(result["invalid_mid_rows"], 3)
        self.assertEqual(result["positive_mid_rows"], 1)

    def test_source_timestamp_classification(self):
        features = [{"ts": 100.0}]
        raw = [{"received_at": "1970-01-01T00:01:41+00:00", "message": {"ts": 100_000_000, "type": "ob_l1"}}]
        result = classify_timestamp_sources(features, raw)
        self.assertIn("processing/state-update wall-clock", result["feature_tape_ts"])
        self.assertIn("local collector receive", result["raw_received_at"])
        self.assertIn("venue-supplied message event timestamp", result["raw_message_t_or_ts"])


if __name__ == "__main__":
    unittest.main()
