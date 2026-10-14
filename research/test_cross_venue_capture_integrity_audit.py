import gzip, json, tempfile, unittest
from pathlib import Path
from research.cross_venue_capture_integrity_audit import audit_delta_continuity, audit_files
from research.cross_venue_aligned_capture_v1 import parse_binance_depth

class CaptureIntegrityAuditTests(unittest.TestCase):
    def test_depth_parser_has_optional_pu(self):
        self.assertIsNone(parse_binance_depth({'U': 1, 'u': 2})['previous_update_id'])
        self.assertEqual(parse_binance_depth({'U': 1, 'u': 2, 'pu': 1})['previous_update_id'], 1)

    def test_delta_timestamp_non_decreasing(self):
        self.assertTrue(audit_delta_continuity({'engine_ts_s': 2}, {'engine_ts_s': 2}))
        self.assertTrue(audit_delta_continuity({'engine_ts_s': 3}, {'engine_ts_s': 2}))
        self.assertFalse(audit_delta_continuity({'engine_ts_s': 1}, {'engine_ts_s': 2}))
        self.assertFalse(audit_delta_continuity({}, {'engine_ts_s': 2}))

    def test_audit_passes_complete_synthetic_archive(self):
        rows = [
            {'venue':'binance','kind':'depthUpdate','previous_update_id':10,'final_update_id':11},
            {'venue':'binance','kind':'depthUpdate','previous_update_id':11,'final_update_id':12},
            {'venue':'binance','kind':'aggTrade','trade_id':100,'is_backfilled':False},
            {'venue':'binance','kind':'aggTrade','trade_id':101,'is_backfilled':True},
            {'venue':'delta','kind':'ob_l2_snapshot','engine_ts_s':2},
            {'venue':'delta','kind':'ob_l2_snapshot','engine_ts_s':2},
        ]
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'session.jsonl.gz'
            with gzip.open(p,'wt',encoding='utf-8') as f:
                for row in rows: f.write(json.dumps(row)+'\n')
            report=audit_files([p])
        self.assertEqual(report['verdict'],'PASS')
        self.assertEqual(report['binance_depth']['pu_missing'],0)
        self.assertEqual(report['binance_aggtrade']['backfilled_rows'],1)

    def test_audit_fails_closed_on_gaps_and_backwards_delta_time(self):
        rows = [
            {'venue':'binance','kind':'depthUpdate','previous_update_id':10,'final_update_id':11},
            {'venue':'binance','kind':'depthUpdate','previous_update_id':15,'final_update_id':16},
            {'venue':'binance','kind':'aggTrade','trade_id':100},
            {'venue':'binance','kind':'aggTrade_gap','gap_start_id':101,'gap_end_id':102},
            {'venue':'binance','kind':'aggTrade','trade_id':103},
            {'venue':'delta','kind':'ob_l2_snapshot','engine_ts_s':3},
            {'venue':'delta','kind':'ob_l2_snapshot','engine_ts_s':2},
        ]
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'session.jsonl.gz'
            with gzip.open(p,'wt',encoding='utf-8') as f:
                for row in rows: f.write(json.dumps(row)+'\n')
            report=audit_files([p])
        self.assertEqual(report['verdict'],'FAIL_CLOSED')
        self.assertGreater(report['binance_depth']['continuity_gaps'],0)
        self.assertEqual(report['binance_aggtrade']['gap_markers'],1)
        self.assertEqual(report['delta_l2']['timestamp_backwards_or_invalid'],1)

if __name__ == '__main__': unittest.main()
