import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from research.delta_market_data_harvester_v1 import harvest, _atomic_json, MAX_CANDLES

class FakeResponse:
    def __init__(self, payload): self.payload = payload
    def raise_for_status(self): pass
    def json(self): return self.payload

class FakeSession:
    def __init__(self): self.calls=[]
    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append((url,params))
        if url.endswith('/v2/products'):
            return FakeResponse({'success':True,'result':[{'id':27,'symbol':'BTCUSD','contract_type':'perpetual_futures','state':'live','tick_size':'0.5'}]})
        if url.endswith('/v2/tickers'):
            return FakeResponse({'success':True,'result':[{'symbol':'BTCUSD','mark_price':'100','funding_rate':'0.0001','oi':'3'}]})
        if '/v2/l2orderbook/' in url:
            return FakeResponse({'success':True,'result':{'symbol':'BTCUSD','buy':[],'sell':[]}})
        if '/v2/history/candles' in url:
            start=params['start']
            return FakeResponse({'success':True,'result':[{'time':start+60,'open':'1','high':'2','low':'1','close':'2','volume':'3'},{'time':start+60,'open':'1','high':'2','low':'1','close':'2','volume':'3'}]})
        raise AssertionError('unexpected endpoint '+url)

class HarvesterTests(unittest.TestCase):
    def test_harvests_all_six_series_and_deduplicates_timestamps(self):
        with tempfile.TemporaryDirectory() as td:
            session=FakeSession()
            result=harvest(['BTCUSD'],Path(td),session=session,now_ts=1800000000,max_candles=10)
            self.assertEqual(result['product_count'],1)
            self.assertEqual(result['ticker_count'],1)
            self.assertEqual(result['orderbook_count'],1)
            self.assertEqual(result['candle_series'],6)
            self.assertEqual(result['candle_rows'],6)
            self.assertFalse(result['real_orders'])
            data=json.loads(Path(result['path']).read_text())
            self.assertEqual(len(data['candle_sets']),6)
            self.assertTrue(data['authority']['private_account_data_used'] is False)
            self.assertEqual(len([c for c in session.calls if '/history/candles' in c[0]]),6)
    def test_rejects_more_than_exchange_response_limit(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError): harvest(['BTCUSD'],Path(td),session=FakeSession(),now_ts=1800000000,max_candles=MAX_CANDLES+1)
    def test_unknown_symbol_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(RuntimeError,'No product metadata'):
                harvest(['FAKECOIN'],Path(td),session=FakeSession(),now_ts=1800000000,max_candles=10)
    def test_atomic_json_does_not_emit_nonfinite_values(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError): _atomic_json(Path(td)/'bad.json',{'x':float('nan')})
    def test_symbols_are_deduplicated_and_normalized(self):
        with tempfile.TemporaryDirectory() as td:
            result=harvest(['btcusd','BTCUSD'],Path(td),session=FakeSession(),now_ts=1800000000,max_candles=2)
            self.assertEqual(result['symbols'],['BTCUSD'])

if __name__=='__main__': unittest.main()
