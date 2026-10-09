import unittest
from research.multi_timeframe_context_v1 import build,describe

def bars(n,trend=1.0):
 out=[]
 for i in range(n):
  c=100+i*trend; out.append({'timestamp':i*60,'open':c-trend*.2,'high':c+1,'low':c-1,'close':c,'volume':1})
 return out
class MultiTimeframeTests(unittest.TestCase):
 def test_trend_detects_uptrend(self): self.assertEqual(describe(bars(100))['direction'],'BULLISH')
 def test_insufficient_history_is_not_directional(self): self.assertEqual(describe(bars(20))['direction'],'UNKNOWN')
 def test_context_never_enables_execution(self):
  x=build({'symbol':'BTCUSD','candles':{k:bars(100) for k in ('1m','5m','15m','1h','4h')}})
  self.assertEqual(x['higher_timeframe_alignment'],'BULLISH'); self.assertFalse(x['live_execution_enabled']); self.assertFalse(x['real_orders'])
if __name__=='__main__':unittest.main()
