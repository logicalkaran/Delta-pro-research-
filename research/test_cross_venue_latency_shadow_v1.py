import unittest
from research.cross_venue_latency_shadow_v1 import summarize, add, parse_binance_quote, EVENTS, STATUS, LOCK

class CrossVenueShadowTests(unittest.TestCase):
 def setUp(self):
  with LOCK: EVENTS.clear(); STATUS.clear()
 def test_summary_is_explicitly_dry_run(self):
  r=summarize();self.assertFalse(r['real_orders']);self.assertFalse(r['private_api']);self.assertFalse(r['credentials_used'])
 def test_arrival_lag_sign_convention(self):
  t=1000.0
  add('binance',t,None,100,101,'test');add('delta_india',t+.02,None,100,101,'test')
  r=summarize();self.assertEqual(r['arrival_lag']['nearest_pairs_within_250ms'],1)
  self.assertAlmostEqual(r['arrival_lag']['delta_receive_minus_binance_receive_ms_p50'],20,places=4)
 def test_binance_partial_depth_payload_schema(self):
  q=parse_binance_quote({'lastUpdateId':1,'bids':[['100.0','3.0']],'asks':[['101.0','4.0']]})
  self.assertEqual(q,(None,100.0,101.0))
 def test_v42_classifier_runs_without_enabling_execution(self):
  add('binance',1000,None,100,101,'test');add('delta_india',1000.01,None,100.1,101.1,'test')
  r=summarize();self.assertIsNotNone(r['cross_venue_edge_v42_dry_run'])
  self.assertIn(r['cross_venue_edge_v42_dry_run']['state'],{'VENUE_CONFIRMATION','MILD_DIVERGENCE','DIVERGENCE'})
  self.assertFalse(r['real_orders'])
 def test_invalid_quotes_ignored(self):
  add('binance',1000,None,0,1,'test')
  with LOCK:self.assertEqual(len(EVENTS),0)
if __name__=='__main__':unittest.main()
