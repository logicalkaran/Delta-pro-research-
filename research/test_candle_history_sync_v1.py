import unittest
from unittest.mock import patch
from research import candle_history_sync_v1 as c

class CandleSyncTests(unittest.TestCase):
    def test_normalizes_newest_first_and_deduplicates(self):
        rows=[{'time':120,'open':2,'high':3,'low':1,'close':2.5,'volume':4},{'time':60,'open':1,'high':2,'low':1,'close':2,'volume':3},{'time':120,'open':2,'high':4,'low':1,'close':3,'volume':5}]
        with patch.object(c.urllib.request,'urlopen') as u:
            import json
            class R:
                def __enter__(self): return self
                def __exit__(self,*a): pass
                def read(self): return json.dumps({'success':True,'result':rows}).encode()
            u.return_value=R()
            got=c.fetch('1m',3600)
        self.assertEqual([x['timestamp'] for x in got],[60,120]); self.assertEqual(got[-1]['high'],4)
    def test_rejects_invalid_ohlc(self):
        import json
        class R:
            def __enter__(self): return self
            def __exit__(self,*a): pass
            def read(self): return json.dumps({'success':True,'result':[{'time':1,'open':2,'high':1,'low':1,'close':2,'volume':0}]}).encode()
        with patch.object(c.urllib.request,'urlopen',return_value=R()): self.assertEqual(c.fetch('1m',3600),[])

if __name__=='__main__': unittest.main()
