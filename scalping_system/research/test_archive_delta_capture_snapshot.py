import hashlib, json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from research.archive_delta_capture_snapshot import SnapshotError, archive_snapshot
class Tests(unittest.TestCase):
 def setUp(self): self.t=tempfile.TemporaryDirectory(); self.root=Path(self.t.name); self.src=self.root/'src.jsonl'; self.out=self.root/'archive'
 def tearDown(self): self.t.cleanup()
 def test_hash_metadata_source_unchanged_and_bad_lines(self):
  data=b'{"received_at":1791555832.1,"ts":123}\nnot-json\n{"receive_ts":1791555833.2}\n'; self.src.write_bytes(data)
  dest,mp,m=archive_snapshot(self.src,self.out); self.assertEqual(dest.read_bytes(),data); self.assertEqual(self.src.read_bytes(),data); self.assertEqual(m['sha256'],hashlib.sha256(data).hexdigest()); self.assertEqual(m['line_count'],3); self.assertEqual(m['malformed_json_lines'],1); self.assertEqual(m['first_receive_timestamp_epoch_seconds'],'1791555832.1'); self.assertTrue(json.loads(mp.read_text())['research_only'])
 def test_collision_never_overwrites(self):
  self.src.write_text('{"received_at":1}\n'); a,_,_=archive_snapshot(self.src,self.out); b,_,_=archive_snapshot(self.src,self.out); self.assertNotEqual(a,b); self.assertTrue(a.exists())
 def test_missing_and_empty(self):
  with self.assertRaises(SnapshotError): archive_snapshot(self.root/'missing',self.out)
  self.src.write_bytes(b'')
  with self.assertRaises(SnapshotError): archive_snapshot(self.src,self.out)
 def test_change_during_hash_aborts_and_cleans_temps(self):
  self.src.write_text('{"received_at":1}\n'); import research.archive_delta_capture_snapshot as mod; real=mod._hash; done=False
  def mutate(p):
   nonlocal done
   if not done: done=True; self.src.write_text('{"received_at":2}\n')
   return real(p)
  with patch.object(mod,'_hash',side_effect=mutate):
   with self.assertRaises(SnapshotError): archive_snapshot(self.src,self.out)
  self.assertEqual(list(self.out.glob('*.jsonl')),[]); self.assertEqual(list(self.out.glob('*.metadata.json')),[]); self.assertEqual(list(self.out.glob('.*.tmp')),[])
 def test_append_during_copy_keeps_consistent_prefix(self):
  self.src.write_text('{"received_at":1}\n'); import research.archive_delta_capture_snapshot as mod; real=mod._hash; appended=False
  def append_record(path):
   nonlocal appended
   if not appended: appended=True; self.src.write_text(self.src.read_text()+'{"received_at":2}\n')
   return real(path)
  with patch.object(mod,'_hash',side_effect=append_record): dest,_,meta=archive_snapshot(self.src,self.out)
  self.assertEqual(dest.read_text(),'{"received_at":1}\n'); self.assertEqual(meta['line_count'],1); self.assertEqual(self.src.read_text(),'{"received_at":1}\n{"received_at":2}\n')
if __name__=='__main__': unittest.main()
