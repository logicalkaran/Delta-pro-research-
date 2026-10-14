import unittest
from unittest.mock import patch
from research import cross_venue_aligned_capture_v1 as capture

class BinanceTradeHealerTests(unittest.TestCase):
    def setUp(self):
        self.healer = capture.BinanceTradeHealer()
        self.rows = []
        self.emit_patch = patch.object(capture, 'emit_raw', side_effect=self.rows.append)
        self.emit_patch.start()
        self.counts_patch = patch.dict(capture.COUNTS, {
            'binance_aggTrade':0, 'aggtrade_gaps_detected':0,
            'aggtrade_backfill_successes':0, 'aggtrade_backfill_failures':0,
            'aggtrade_backfilled_rows':0, 'bad_rows':0}, clear=False)
        self.counts_patch.start()
        self.status_patch = patch.dict(capture.STATUS, {'binance':'connected_synced'}, clear=False)
        self.status_patch.start()

    def tearDown(self):
        self.status_patch.stop(); self.counts_patch.stop(); self.emit_patch.stop()

    @staticmethod
    def trade(a):
        return {'a':a,'p':'100.0','q':'0.01','m':False,'E':1000+a,'T':1000+a}

    def test_successful_gap_backfill_does_not_retrigger_same_gap(self):
        async def fake_backfill(start, end):
            self.assertEqual((start,end),(11,12))
            self.rows.extend([{'venue':'binance','kind':'aggTrade','trade_id':11,'is_backfilled':True},
                              {'venue':'binance','kind':'aggTrade','trade_id':12,'is_backfilled':True}])
            return True, 2
        with patch.object(capture, 'backfill_aggtrade_gap', side_effect=fake_backfill) as backfill:
            self.healer.process_live_trade(self.trade(10))
            self.healer.process_live_trade(self.trade(13))
        backfill.assert_called_once_with(11,12)
        self.assertEqual(capture.COUNTS['aggtrade_backfill_successes'],1)
        self.assertFalse(any(r.get('kind')=='aggTrade_gap' for r in self.rows))
        self.assertEqual(self.healer.expected_a,14)

    def test_failed_backfill_writes_explicit_gap_marker(self):
        async def fake_backfill(start, end): return False, 0
        with patch.object(capture, 'backfill_aggtrade_gap', side_effect=fake_backfill):
            self.healer.process_live_trade(self.trade(10))
            self.healer.process_live_trade(self.trade(13))
        markers=[r for r in self.rows if r.get('kind')=='aggTrade_gap']
        self.assertEqual(len(markers),1)
        self.assertEqual((markers[0]['gap_start_id'],markers[0]['gap_end_id']),(11,12))
        self.assertEqual(capture.COUNTS['aggtrade_backfill_failures'],1)

    def test_duplicate_live_trade_is_ignored(self):
        self.healer.process_live_trade(self.trade(10))
        count=len(self.rows)
        self.healer.process_live_trade(self.trade(10))
        self.assertEqual(len(self.rows),count)

if __name__ == '__main__': unittest.main()
