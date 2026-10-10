import gzip
import json
import tempfile
import unittest
from pathlib import Path

from research.offline_cross_venue_batch_v1 import (
    audit_and_calibrate, read_partition, iter_rows, run_offline
)

class OfflineBatchIntegrityTests(unittest.TestCase):
    def test_valid_partition_preserves_rows_and_validates_trailer(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "session_s_part_0001.jsonl.gz"
            rows = [{"n": 1}, {"n": 2}]
            with gzip.open(p, "wt", encoding="utf-8") as f:
                for row in rows:
                    f.write(json.dumps(row) + "\n")
            status = {}
            self.assertEqual(list(read_partition(p, True, status)), rows)
            self.assertEqual(status["gzip_integrity"], "VALID")

    def test_truncated_final_partition_keeps_complete_prefix_and_drops_partial_line(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "session_s_part_0001.jsonl.gz"
            payload = (json.dumps({"n": 1}) + "\n" + '{"n":2').encode()
            p.write_bytes(gzip.compress(payload)[:-8])
            status = {}
            self.assertEqual(list(read_partition(p, True, status)), [{"n": 1}])
            self.assertEqual(status["gzip_integrity"], "RECOVERED_TRUNCATED_FINAL_PARTITION")
            self.assertGreater(status["dropped_trailing_partial_record_bytes"], 0)

    def test_corrupt_final_gzip_trailer_preserves_preceding_json_records(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "session_s_part_0001.jsonl.gz"
            blob = bytearray(gzip.compress((json.dumps({"n": 1}) + chr(10) + json.dumps({"n": 2}) + chr(10)).encode()))
            blob[-8] ^= 0xFF  # corrupt CRC trailer; zlib raises while reading final block
            p.write_bytes(blob)
            status = {}
            self.assertEqual(list(read_partition(p, True, status)), [{"n": 1}, {"n": 2}])
            self.assertEqual(status["gzip_integrity"], "RECOVERED_TRUNCATED_FINAL_PARTITION")

    def test_truncated_nonfinal_partition_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "session_s_part_0001.jsonl.gz"
            p.write_bytes(gzip.compress((json.dumps({"n": 1}) + "\n").encode())[:-8])
            with self.assertRaises(ValueError):
                list(read_partition(p, False, {}))

    def test_audit_requires_delta_sequence_fields(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            p = d / "session_s_part_0001.jsonl.gz"
            rows = [
                {"venue":"binance","kind":"aggTrade","receive_mono_s":1.0,"engine_event_ts_s":1000.0,"trade_id":1,"quantity_btc":1.0,"aggressor_side":"BUY"},
                {"venue":"delta","kind":"ob_l2_snapshot","receive_mono_s":1.1,"engine_ts_s":1000.1,"best_bid":99,"best_ask":101,"bid_levels":[[99,1],[98,1],[97,1],[96,1],[95,1]],"ask_levels":[[101,1],[102,1],[103,1],[104,1],[105,1]]},
            ]
            with gzip.open(p, "wt", encoding="utf-8") as f:
                for row in rows:
                    f.write(json.dumps(row) + "\n")
            report, bucket, first = audit_and_calibrate("s", d)
            self.assertEqual(report["status"], "FAIL_CLOSED")
            self.assertEqual(report["delta_sequence_status"], "UNVERIFIABLE_MISSING_SEQUENCE_FIELDS")
            self.assertGreater(bucket, 0)
            self.assertEqual(first, 1.0)

    def test_audit_detects_sequence_gap_and_accepts_complete_fixture(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            p = d / "session_s_part_0001.jsonl.gz"
            rows = [
                {"venue":"binance","kind":"aggTrade","receive_mono_s":1.0,"engine_event_ts_s":1000.0,"trade_id":1,"quantity_btc":1.0,"aggressor_side":"BUY"},
                {"venue":"delta","kind":"ob_l2_snapshot","receive_mono_s":1.1,"engine_ts_s":1000.1,"sequence":10,"best_bid":99,"best_ask":101,"bid_levels":[[99,1],[98,1],[97,1],[96,1],[95,1]],"ask_levels":[[101,1],[102,1],[103,1],[104,1],[105,1]]},
                {"venue":"binance","kind":"aggTrade","receive_mono_s":1.2,"engine_event_ts_s":1000.2,"trade_id":2,"quantity_btc":1.0,"aggressor_side":"SELL"},
                {"venue":"delta","kind":"ob_l2_snapshot","receive_mono_s":1.3,"engine_ts_s":1000.3,"sequence":11,"best_bid":99,"best_ask":101,"bid_levels":[[99,1],[98,1],[97,1],[96,1],[95,1]],"ask_levels":[[101,1],[102,1],[103,1],[104,1],[105,1]]},
                {"venue":"binance","kind":"depthUpdate","receive_mono_s":1.4,"engine_event_ts_s":1000.4,"first_update_id":100,"final_update_id":110,"previous_update_id":90},
                {"venue":"binance","kind":"depthUpdate","receive_mono_s":1.5,"engine_event_ts_s":1000.5,"first_update_id":120,"final_update_id":130,"previous_update_id":110},
            ]
            with gzip.open(p, "wt", encoding="utf-8") as f:
                for row in rows:
                    f.write(json.dumps(row) + "\n")
            report, bucket, first = audit_and_calibrate("s", d)
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(report["delta_sequence_status"], "VERIFIABLE")
            self.assertGreater(bucket, 0)
            rows[3]["sequence"] = 13
            p2 = d / "session_g_part_0001.jsonl.gz"
            with gzip.open(p2, "wt", encoding="utf-8") as f:
                for row in rows:
                    f.write(json.dumps(row) + "\n")
            bad, _, _ = audit_and_calibrate("g", d)
            self.assertEqual(bad["status"], "FAIL_CLOSED")
            self.assertEqual(bad["counts"]["delta_sequence_gaps"], 1)


    def test_binance_depth_audit_uses_previous_update_id_not_nonoverlapping_u_range(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            p = d / "session_s_part_0001.jsonl.gz"
            rows = [
                {"venue":"binance","kind":"aggTrade","receive_mono_s":1.0,"engine_event_ts_s":1000.0,"trade_id":1,"quantity_btc":1.0,"aggressor_side":"BUY"},
                {"venue":"binance","kind":"depthUpdate","receive_mono_s":1.01,"engine_event_ts_s":1000.01,"first_update_id":100,"final_update_id":110,"previous_update_id":90},
                {"venue":"binance","kind":"depthUpdate","receive_mono_s":1.02,"engine_event_ts_s":1000.02,"first_update_id":120,"final_update_id":130,"previous_update_id":110},
                {"venue":"delta","kind":"ob_l2_snapshot","receive_mono_s":1.03,"engine_ts_s":1000.03,"sequence":10,"best_bid":99,"best_ask":101,"bid_levels":[[99,1]],"ask_levels":[[101,1]]},
                {"venue":"delta","kind":"ob_l2_snapshot","receive_mono_s":1.04,"engine_ts_s":1000.04,"sequence":11,"best_bid":99,"best_ask":101,"bid_levels":[[99,1]],"ask_levels":[[101,1]]},
            ]
            with gzip.open(p, "wt", encoding="utf-8") as f:
                for row in rows:
                    f.write(json.dumps(row) + "\n")
            report, _, _ = audit_and_calibrate("s", d)
            self.assertEqual(report["binance_depth_sequence_status"], "VERIFIABLE")
            self.assertEqual(report["counts"].get("binance_depth_sequence_gaps", 0), 0)
            self.assertEqual(report["status"], "PASS")
            rows[2]["previous_update_id"] = 109
            p2 = d / "session_g_part_0001.jsonl.gz"
            with gzip.open(p2, "wt", encoding="utf-8") as f:
                for row in rows:
                    f.write(json.dumps(row) + "\n")
            bad, _, _ = audit_and_calibrate("g", d)
            self.assertEqual(bad["counts"]["binance_depth_sequence_gaps"], 1)
            self.assertEqual(bad["status"], "FAIL_CLOSED")

    def test_delta_trade_timestamp_reordering_is_diagnostic_not_book_clock_failure(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            p = d / "session_s_part_0001.jsonl.gz"
            rows = [
                {"venue":"binance","kind":"aggTrade","receive_mono_s":1.0,"engine_event_ts_s":1000.0,"trade_id":1,"quantity_btc":1.0,"aggressor_side":"BUY"},
                {"venue":"delta","kind":"trade","receive_mono_s":1.1,"engine_trade_ts_s":1000.2,"price":100,"quantity_contract_units":1},
                {"venue":"delta","kind":"trade","receive_mono_s":1.2,"engine_trade_ts_s":1000.1,"price":100,"quantity_contract_units":1},
                {"venue":"delta","kind":"ob_l2_snapshot","receive_mono_s":1.3,"engine_ts_s":1000.3,"sequence":10,"best_bid":99,"best_ask":101,"bid_levels":[[99,1]],"ask_levels":[[101,1]]},
                {"venue":"binance","kind":"depthUpdate","receive_mono_s":1.4,"engine_event_ts_s":1000.4,"first_update_id":100,"final_update_id":110,"previous_update_id":90},
                {"venue":"binance","kind":"depthUpdate","receive_mono_s":1.5,"engine_event_ts_s":1000.5,"first_update_id":120,"final_update_id":130,"previous_update_id":110},
            ]
            with gzip.open(p, "wt", encoding="utf-8") as f:
                for row in rows:
                    f.write(json.dumps(row) + "\n")
            report, _, _ = audit_and_calibrate("s", d)
            self.assertEqual(report["counts"].get("trade_event_timestamp_out_of_order"), 1)
            self.assertEqual(report["counts"].get("timestamp_regressions", 0), 0)
            self.assertEqual(report["status"], "PASS")

    def test_offline_batch_replays_trigger_and_marks_out_without_execution(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            archive = root / "archive"
            out = root / "out"
            archive.mkdir()
            p = archive / "session_s_part_0001.jsonl.gz"
            delta_bids = [[100,2],[99,2],[98,2],[97,2],[96,2]]
            delta_asks = [[102,2],[103,2],[104,2],[105,2],[106,2]]
            bin_bids = [[100,10],[99,10],[98,10],[97,10],[96,10]]
            bin_asks = [[102,1],[103,1],[104,1],[105,1],[106,1]]
            rows = [
                {"venue":"binance","kind":"aggTrade","receive_mono_s":1.0+i*0.01,"engine_event_ts_s":1000.0+i*0.01,"trade_id":i+1,"quantity_btc":0.1,"aggressor_side":"BUY","book_synced":True}
                for i in range(21)
            ]
            rows += [
                {"venue":"delta","kind":"ob_l2_snapshot","receive_mono_s":1.22,"engine_ts_s":1000.22,"best_bid":100,"best_ask":102,"bid_levels":delta_bids,"ask_levels":delta_asks},
                {"venue":"binance","kind":"depthUpdate","receive_mono_s":1.23,"engine_event_ts_s":1000.23,"book_synced":True,"bid_levels_top5_btc":bin_bids,"ask_levels_top5_btc":bin_asks},
                {"venue":"delta","kind":"ob_l2_snapshot","receive_mono_s":901.0,"engine_ts_s":1900.0,"best_bid":100,"best_ask":102,"bid_levels":delta_bids,"ask_levels":delta_asks},
                {"venue":"binance","kind":"depthUpdate","receive_mono_s":901.01,"engine_event_ts_s":1900.01,"book_synced":True,"bid_levels_top5_btc":bin_bids,"ask_levels_top5_btc":bin_asks},
                {"venue":"binance","kind":"aggTrade","receive_mono_s":901.02,"engine_event_ts_s":1900.02,"trade_id":22,"quantity_btc":0.1,"aggressor_side":"SELL","book_synced":True},
                {"venue":"delta","kind":"trade","receive_mono_s":901.1,"engine_trade_ts_s":1900.1,"price":100,"quantity_contract_units":3,"role":"m"},
                {"venue":"delta","kind":"ob_l2_snapshot","receive_mono_s":901.23,"engine_ts_s":1900.23,"best_bid":100,"best_ask":102,"bid_levels":delta_bids,"ask_levels":delta_asks},
                {"venue":"delta","kind":"ob_l2_snapshot","receive_mono_s":916.2,"engine_ts_s":1915.2,"best_bid":100,"best_ask":102,"bid_levels":delta_bids,"ask_levels":delta_asks},
            ]
            with gzip.open(p, "wt", encoding="utf-8") as f:
                for row in rows:
                    f.write(json.dumps(row) + "\n")
            summary = run_offline("s", archive, out, 0.1, 1.0, 1.0, 2.36, 5.90)
            self.assertEqual(summary["status"], "COMPLETE_RESEARCH_ONLY")
            self.assertEqual(summary["queue_replay"]["simulated_fills"], 1)
            self.assertEqual(summary["economics"]["sample_count"], 1)
            self.assertFalse(summary["economics"]["pass"])
            derivative_rows = [json.loads(x) for x in (out / "cross_venue_s_derivative.jsonl").read_text().splitlines()]
            self.assertEqual(sum(r.get("decision") == "CANDIDATE_WITH_200MS_RESPONSE" for r in derivative_rows), 1)

if __name__ == "__main__":
    unittest.main()
