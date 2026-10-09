import tempfile,unittest
from pathlib import Path
from research import live_microstructure_forward_worker_v2 as w

class ForwardWorkerTests(unittest.TestCase):
 def test_forward_labels_use_first_observation_at_or_after_horizon(self):
  rows=[{'ts':float(i*10),'mid':100+i} for i in range(40)]
  got=w.label_ready(rows,-1)
  self.assertEqual(got[0]['labels']['60']['future_ts'],60.0)
  self.assertAlmostEqual(got[0]['labels']['60']['move_bps'],600.0)
  self.assertTrue(got[0]['research_only']); self.assertFalse(got[0]['real_orders'])
 def test_not_label_future_without_complete_horizons(self):
  self.assertEqual(w.label_ready([{'ts':0.0,'mid':100.0},{'ts':60.0,'mid':101.0}],-1),[])

 def test_checkpoint_filters_already_processed_rows(self):
  rows=[{'ts':float(i*10),'mid':100+i} for i in range(40)]
  got=w.label_ready(rows,20.0)
  self.assertTrue(got); self.assertGreater(min(r['ts'] for r in got),20.0)
 def test_read_rows_sorts_and_deduplicates(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'rows.jsonl'; p.write_text('{"ts":2,"mid":2}\n{"ts":1,"mid":1}\n{"ts":2,"mid":3}\n')
   got=w.read_rows(p); self.assertEqual([r['ts'] for r in got],[1,2]); self.assertEqual(got[-1]['mid'],3)

if __name__=='__main__': unittest.main()
