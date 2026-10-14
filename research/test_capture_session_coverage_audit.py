import json
import tempfile
import unittest
from pathlib import Path

from research.capture_session_coverage_audit import (
    audit, normalize_epoch, parse_receive, quote_validity, segment_sessions,
)


class CaptureSessionCoverageAuditTests(unittest.TestCase):
    def test_session_segmentation_uses_strictly_greater_than_threshold(self):
        sessions = segment_sessions([0, 30, 60.1, 100])
        self.assertEqual([s["row_count"] for s in sessions], [2, 1, 1])
        self.assertEqual(sessions[1]["duration_seconds"], 0)

    def test_timestamp_normalization(self):
        self.assertEqual(normalize_epoch(1_700_000_000), (1_700_000_000, "seconds"))
        value, kind = normalize_epoch(1_700_000_000_000_000)
        self.assertEqual(kind, "microseconds")
        self.assertEqual(value, 1_700_000_000)
        self.assertEqual(normalize_epoch("bad"), (None, "invalid"))
        self.assertEqual(parse_receive("2026-10-09T00:00:00Z"), parse_receive("2026-10-09T00:00:00+00:00"))

    def test_lag_calculation(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "raw.jsonl"
            source.write_text(json.dumps({"received_at": "2026-10-09T00:00:01Z",
                                          "message": {"type": "trades", "t": 1791504000000000}}) + "\n")
            result = audit(source)
            lag = result["event_to_receive_lag"]
            self.assertEqual(lag["count"], 1)
            self.assertAlmostEqual(lag["median_seconds"], 1)

    def test_malformed_rows_and_missing_event_timestamps(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "raw.jsonl"
            source.write_text("{bad\n" + json.dumps({"received_at": "2026-10-09T00:00:00Z", "message": {"type": "ob_l2"}}) + "\n")
            result = audit(source)
            self.assertEqual(result["rows_read"], 2)
            self.assertEqual(result["malformed_rows"], 1)
            self.assertEqual(result["missing_event_timestamps"], 1)

    def test_control_messages_do_not_inflate_missing_market_event_timestamps(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "raw.jsonl"
            rows = [
                {"received_at": "2026-10-09T00:00:00Z", "message": {"type": "subscriptions", "channels": ["trades"]}},
                {"received_at": "2026-10-09T00:00:01Z", "message": {"type": "ob_l2", "bids": []}},
            ]
            source.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
            result = audit(source)
            self.assertEqual(result["event_timestamp_applicable_rows"], 1)
            self.assertEqual(result["missing_event_timestamps"], 1)
            self.assertEqual(result["non_market_rows_without_event_timestamp"], 1)

    def test_quote_validation(self):
        self.assertEqual(quote_validity({"bp": 100, "ap": 101}), (True, False))
        self.assertEqual(quote_validity({"bp": 102, "ap": 101}), (False, True))
        self.assertEqual(quote_validity({"bp": 0, "ap": 1}), (False, False))
        self.assertEqual(quote_validity({"bp": "nan", "ap": 1}), (False, False))


if __name__ == "__main__":
    unittest.main()
