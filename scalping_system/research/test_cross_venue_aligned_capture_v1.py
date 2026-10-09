import unittest
from research.cross_venue_aligned_capture_v1 import ts_seconds, nearest_quantile, depth_snapshot_bridge, depth_event_follows, count_swept_trade_levels, FLOW, LOCK

class AlignedCaptureTests(unittest.TestCase):
 def test_microsecond_timestamp_normalized(self):self.assertEqual(ts_seconds(1791565645250531),1791565645.250531)
 def test_millisecond_timestamp_normalized(self):self.assertEqual(ts_seconds(1791565645250),1791565645.25)
 def test_seconds_timestamp_preserved(self):self.assertEqual(ts_seconds(1791565645.25),1791565645.25)
 def test_quantile_is_upper_order_statistic(self):self.assertEqual(nearest_quantile([1,2,3,4],.75),3)
 def test_empty_quantile(self):self.assertIsNone(nearest_quantile([],.99))
 def test_snapshot_bridge_requires_update_range_to_cover_snapshot_id(self):
  self.assertTrue(depth_snapshot_bridge(100,105,103))
  self.assertFalse(depth_snapshot_bridge(104,105,103))
  self.assertFalse(depth_snapshot_bridge(100,102,103))
 def test_sweep_requires_distinct_aggressive_trade_prices(self):
  with LOCK:
   FLOW.clear();FLOW.extend([(10.1,1.0,100.0),(10.2,2.0,100.1),(10.3,1.0,100.2),(10.4,-1.0,100.3)])
  self.assertEqual(count_swept_trade_levels(1,100.0,100.3,10.5),3)
  self.assertEqual(count_swept_trade_levels(-1,100.4,100.0,10.5),1)
  with LOCK:FLOW.clear()
 def test_futures_depth_sequence_uses_previous_update_id(self):
  self.assertTrue(depth_event_follows(105,105))
  self.assertFalse(depth_event_follows(105,106))
  self.assertFalse(depth_event_follows(105,None))
if __name__=='__main__':unittest.main()
