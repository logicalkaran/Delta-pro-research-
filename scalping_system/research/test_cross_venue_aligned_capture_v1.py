import unittest
from research.cross_venue_aligned_capture_v1 import ts_seconds, nearest_quantile

class AlignedCaptureTests(unittest.TestCase):
 def test_microsecond_timestamp_normalized(self):self.assertEqual(ts_seconds(1791565645250531),1791565645.250531)
 def test_millisecond_timestamp_normalized(self):self.assertEqual(ts_seconds(1791565645250),1791565645.25)
 def test_seconds_timestamp_preserved(self):self.assertEqual(ts_seconds(1791565645.25),1791565645.25)
 def test_quantile_is_upper_order_statistic(self):self.assertEqual(nearest_quantile([1,2,3,4],.75),3)
 def test_empty_quantile(self):self.assertIsNone(nearest_quantile([],.99))
if __name__=='__main__':unittest.main()
