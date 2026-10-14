import unittest

from research.capture_report_consistency_audit_v1 import evaluate


def fixtures():
    capture = {
        "research_only": True,
        "real_orders": False,
        "counts": {
            "sequence_gaps": 0,
            "aggtrade_gaps_detected": 0,
            "aggtrade_backfill_failures": 0,
            "bad_rows": 0,
            "binance_aggTrade": 10,
            "binance_depthUpdate": 20,
            "delta_ob_l2": 5,
        },
    }
    integrity = {
        "schema": "cross_venue_capture_integrity_audit_v1",
        "verdict": "PASS",
        "binance_aggtrade": {"rows": 10},
        "binance_depth": {"rows": 20},
        "delta_l2": {"rows": 5},
    }
    return capture, integrity


class CaptureReportConsistencyTests(unittest.TestCase):
    def test_clean_matching_reports_pass(self):
        capture, integrity = fixtures()
        self.assertEqual(evaluate(capture, integrity)["verdict"], "PASS")

    def test_sequence_gap_overrides_raw_audit_pass(self):
        capture, integrity = fixtures()
        capture["counts"]["sequence_gaps"] = 1
        result = evaluate(capture, integrity)
        self.assertEqual(result["verdict"], "FAIL_CLOSED")
        self.assertTrue(any("sequence_gaps" in x for x in result["blockers"]))

    def test_counter_mismatch_fails_closed(self):
        capture, integrity = fixtures()
        capture["counts"]["delta_ob_l2"] = 6
        self.assertEqual(evaluate(capture, integrity)["verdict"], "FAIL_CLOSED")

    def test_raw_audit_failure_fails_closed(self):
        capture, integrity = fixtures()
        integrity["verdict"] = "FAIL_CLOSED"
        self.assertEqual(evaluate(capture, integrity)["verdict"], "FAIL_CLOSED")

    def test_missing_counts_fail_closed(self):
        capture, integrity = fixtures()
        del capture["counts"]["sequence_gaps"]
        result = evaluate(capture, integrity)
        self.assertEqual(result["verdict"], "FAIL_CLOSED")
        capture["counts"]["sequence_gaps"] = "not-a-number"
        self.assertEqual(evaluate(capture, integrity)["verdict"], "FAIL_CLOSED")


if __name__ == "__main__":
    unittest.main()
