import hashlib,json,tempfile,unittest
from pathlib import Path
from research.archive_session_inventory_v1 import evaluate
class InventoryTests(unittest.TestCase):
 def setUp(self): self.t=tempfile.TemporaryDirectory(); self.d=Path(self.t.name)
 def tearDown(self): self.t.cleanup()
 def add(self,name,start,end):
  p=self.d/(name+'.jsonl'); data=b'{"received_at":1}\n'; p.write_bytes(data)
  m={'archive_file':p.name,'byte_size':len(data),'sha256':hashlib.sha256(data).hexdigest(),'first_receive_timestamp_epoch_seconds':start,'last_receive_timestamp_epoch_seconds':end,'line_count':1,'malformed_json_lines':0,'research_only':True,'real_orders':False}
  p.with_name(p.stem+'.metadata.json').write_text(json.dumps(m)); return p
 def test_empty_not_ready(self):
  r=evaluate(self.d); self.assertEqual(r['archive_count'],0); self.assertEqual(r['readiness']['verdict'],'NOT_READY')
 def test_overlapping_archives_not_double_counted(self):
  self.add('a',0,7200); self.add('b',3600,10800)
  r=evaluate(self.d); self.assertEqual(r['session_count'],1); self.assertAlmostEqual(r['summed_unique_session_hours'],3.0)
 def test_separated_sessions_and_readiness(self):
  self.add('a',0,7200); self.add('b',200000,207200); self.add('c',400000,407200)
  r=evaluate(self.d); self.assertEqual(r['session_count'],3); self.assertEqual(r['readiness']['verdict'],'READY_FOR_MULTI_SESSION_RESEARCH')
 def test_hash_mismatch_invalid(self):
  p=self.add('a',0,7200); p.write_text('tampered\n'); r=evaluate(self.d); self.assertEqual(r['invalid_archive_count'],1); self.assertEqual(r['session_count'],0)
if __name__=='__main__': unittest.main()
