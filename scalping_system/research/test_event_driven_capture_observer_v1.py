import json
import tempfile
import unittest
from pathlib import Path

from research.event_driven_capture_observer_v1 import normalize_epoch, observe, quote_from


def row(received, message):
    return {"received_at": received, "message": message}


class ObserverTests(unittest.TestCase):
    def run_rows(self, rows):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "raw.jsonl"
        path.write_text("".join(json.dumps(x) + "\n" for x in rows))
        return observe(path)

    def test_timestamp_normalization_and_classification(self):
        seconds, kind = normalize_epoch(1791555832907534)
        self.assertEqual(kind, "microseconds")
        self.assertAlmostEqual(seconds, 1791555832.907534)
        report = self.run_rows([row("2026-10-09T14:23:52Z", {"type":"ob_l1", "ts":1791555832907534, "bp":100, "ap":101})])
        self.assertEqual(report["timestamp_source_classification"]["event_timestamp_units"], {"microseconds":1})

    def test_baseline_sampling(self):
        report = self.run_rows([row("2026-10-09T14:23:52Z", {"type":"ob_l1", "ts":1000000, "bp":100, "ap":101})])
        self.assertEqual(report["periodic_sample_count"], 1)
        self.assertIn("periodic_1s", report["sample_rows"][0]["trigger_reasons"])

    def test_event_triggers_and_cooldown(self):
        rows = [
            row("2026-10-09T14:23:52.000Z", {"type":"ob_l1", "ts":1791555832000000, "bp":100, "ap":101}),
            row("2026-10-09T14:23:52.100Z", {"type":"trades", "t":1791555832100000, "p":100.5, "s":2}),
            row("2026-10-09T14:23:52.200Z", {"type":"trades", "t":1791555832200000, "p":100.5, "s":1}),
            row("2026-10-09T14:23:52.400Z", {"type":"trades", "t":1791555832400000, "p":100.5, "s":1}),
        ]
        report = self.run_rows(rows)
        trade_samples = [s for s in report["sample_rows"] if s["trade_print"]]
        self.assertEqual(len(trade_samples), 2)
        self.assertEqual(trade_samples[0]["channel"], "trades")
        self.assertEqual(trade_samples[0]["event_timestamp_field"], "t")
        self.assertEqual(report["trigger_reason_counts"]["trade_print"], 2)
        self.assertEqual(report["periodic_only_sample_count"] + report["event_only_sample_count"] + report["both_periodic_and_event_sample_count"], report["sample_count"])

    def test_trade_timestamp_prefers_t_when_both_fields_exist(self):
        report = self.run_rows([
            row("2026-10-09T14:23:52.000Z", {"type":"ob_l1", "ts":1791555832000000, "bp":100, "ap":101}),
            row("2026-10-09T14:23:52.300Z", {"type":"trades", "t":1791555832300000, "ts":1791555832999999, "p":100.5, "s":2}),
        ])
        trade_sample = next(s for s in report["sample_rows"] if s["channel"] == "trades")
        self.assertEqual(trade_sample["event_timestamp_field"], "t")
        self.assertAlmostEqual(trade_sample["event_timestamp"], 1791555832.3)
        self.assertEqual(trade_sample["quote_event_timestamp_field"], "ts")
        self.assertEqual(report["periodic_only_sample_count"], 1)
        self.assertEqual(report["event_only_sample_count"], 1)
        self.assertEqual(report["both_periodic_and_event_sample_count"], 0)
        self.assertTrue(report["trigger_reason_counts_may_overlap"])

    def test_invalid_and_crossed_quotes_rejected(self):
        self.assertEqual(quote_from({"bp": 102, "ap": 101})[1], "crossed_quote")
        report = self.run_rows([
            row("2026-10-09T14:23:52Z", {"type":"ob_l1", "ts":1791555832000000, "bp":0, "ap":1}),
            row("2026-10-09T14:23:53Z", {"type":"ob_l1", "ts":1791555833000000, "bp":102, "ap":101}),
        ])
        self.assertEqual(report["invalid_quotes"], 2)
        self.assertEqual(report["crossed_quotes"], 1)
        self.assertEqual(report["sample_count"], 0)

    def test_malformed_input_counted(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "raw.jsonl"
        path.write_text("{broken\n" + json.dumps({"received_at":"2026-10-09T14:23:52Z", "message":{}}) + "\n")
        report = observe(path)
        self.assertEqual(report["rows_read"], 2)
        self.assertEqual(report["malformed_rows"], 1)
        self.assertEqual(report["missing_fields"]["message.ts_or_t"], 1)

if __name__ == "__main__":
    unittest.main()
