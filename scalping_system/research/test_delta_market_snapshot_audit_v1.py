import unittest
from research.delta_market_snapshot_audit_v1 import analyze, candle_audit

class SnapshotAuditTests(unittest.TestCase):
    def sample(self):
        return {'collected_at':'2026-10-09T00:00:00+00:00','products':[{'symbol':'BTCUSD','id':27,'contract_type':'perpetual_futures'}],'tickers':[{'symbol':'BTCUSD','mark_price':'101','spot_price':'100','funding_rate':'0.001'}],'orderbooks':{'BTCUSD':{'result':{'buy':[{'price':'100','size':10}],'sell':[{'price':'101','size':5}]}}},'candle_sets':{'BTCUSD|price|1m':{'candles':[{'time':60,'open':100,'high':101,'low':99,'close':100,'volume':10},{'time':120,'open':100,'high':102,'low':100,'close':101,'volume':12}]},'BTCUSD|open_interest|1h':{'candles':[{'time':3600,'open':10,'high':11,'low':9,'close':10,'volume':None},{'time':7200,'open':10,'high':12,'low':10,'close':11,'volume':None}]}},'failures':[]}
    def test_basis_spread_and_imbalance(self):
        a=analyze(self.sample(),'BTCUSD')
        self.assertAlmostEqual(a['derived']['mark_vs_spot_basis_bps'],100)
        self.assertAlmostEqual(a['derived']['orderbook_spread_bps'],(1/100.5)*10000)
        self.assertAlmostEqual(a['derived']['top20_depth_imbalance'],1/3)
        self.assertTrue(a['authority']['research_only']); self.assertFalse(a['authority']['real_orders'])
    def test_candle_gap_and_invalid_detection(self):
        a=candle_audit([{'time':60,'open':1,'high':2,'low':1,'close':2},{'time':240,'open':1,'high':2,'low':1,'close':2},{'time':300,'open':2,'high':1,'low':1,'close':1}],60)
        self.assertEqual(a['invalid_rows'],1); self.assertEqual(a['gap_count'],1)
    def test_funding_series_allows_negative_and_zero_rates_without_price_returns(self):
        a=candle_audit([{'time':3600,'open':-0.01,'high':0.02,'low':-0.02,'close':0.0},{'time':7200,'open':0.0,'high':0.01,'low':-0.01,'close':-0.005}],3600,allow_nonpositive=True)
        self.assertEqual(a['rows_valid'],2); self.assertEqual(a['invalid_rows'],0); self.assertEqual(a['return_count'],0)
    def test_missing_market_data_is_nonfatal_and_not_healthy_claim(self):
        a=analyze({'products':[],'tickers':[],'orderbooks':{},'candle_sets':{},'failures':[]},'BTCUSD')
        self.assertIsNone(a['derived']['orderbook_spread_bps']); self.assertTrue(a['data_quality']['all_series_empty'])

if __name__=='__main__': unittest.main()
