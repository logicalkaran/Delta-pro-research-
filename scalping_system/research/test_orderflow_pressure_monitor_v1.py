import unittest
from research.orderflow_pressure_monitor_v1 import Monitor,ts_seconds

class OrderflowPressureTests(unittest.TestCase):
 def rec(self,ts,msg):return {'received_at':f'2026-10-09T17:00:{ts:02d}+00:00','message':msg}
 def test_trade_sign_and_cvd(self):
  m=Monitor();m.ingest(self.rec(1,{'type':'ob_l1','ts':1791565201000000,'bp':'100','bs':'10','ap':'101','as':'10'}))
  m.ingest(self.rec(2,{'type':'trades','ts':1791565202000000,'p':'101','s':'600'}))
  m.ingest(self.rec(3,{'type':'trades','ts':1791565203000000,'p':'100','s':'100'}))
  self.assertEqual(m.trades[-2]['side'],'buy');self.assertEqual(m.trades[-1]['side'],'sell');self.assertEqual(m.cvd,500)
 def test_vamp_uses_opposite_side_sizes(self):
  m=Monitor();m.ingest({'received_at':'2026-10-09T17:00:01+00:00','message':{'type':'ob_l1','ts':1791565201000000,'bp':'100','bs':'90','ap':'101','as':'10'}})
  s=m.snapshot(now=1791565202)
  self.assertAlmostEqual(s['vamp'],(100*10+101*90)/100)
  self.assertGreater(s['vamp_displacement_bps'],0)
 def test_l1_ofi_computes_queue_changes(self):
  m=Monitor()
  for sec,bid,bq,ask,aq in [(1,100,10,101,10),(2,100,20,101,8)]:
   m.ingest({'received_at':f'2026-10-09T17:00:0{sec}+00:00','message':{'type':'ob_l1','ts':1791565200000000+sec*1000000,'bp':bid,'bs':bq,'ap':ask,'as':aq}})
  self.assertEqual(m.ofi_events[-1]['ofi'],12)
 def test_stale_data_and_latency_fail_closed(self):
  m=Monitor();m.ingest({'received_at':'2026-10-09T17:00:01+00:00','message':{'type':'ob_l1','ts':1791565201000000,'bp':'100','bs':'10','ap':'101','as':'10'}})
  s=m.snapshot(now=1791565210)
  self.assertFalse(s['data_quality_ok']);self.assertFalse(s['latency_gate_passed']);self.assertFalse(s['real_orders'])

 def test_three_to_one_volume_ratio_is_only_a_candidate(self):
  m=Monitor()
  m.ingest({'received_at':'2026-10-09T17:00:01+00:00','message':{'type':'ob_l1','ts':1791565201000000,'bp':'100','bs':'100','ap':'101','as':'100'}})
  for t,px,qty in [(2,101,600),(3,100,100)]:
   m.ingest({'received_at':f'2026-10-09T17:00:0{t}+00:00','message':{'type':'trades','ts':1791565200000000+t*1000000,'p':str(px),'s':str(qty)}})
  s=m.snapshot(now=1791565204)
  self.assertTrue(s['buy_sell_3x_candidate'])
  self.assertFalse(s['real_orders'])
  self.assertEqual(s['policy'],'OBSERVE_AND_LABEL_ONLY_NO_ENTRY_SIGNAL')
 def test_ofi_vamp_disagreement_is_exposed(self):
  m=Monitor()
  for t,bq,aq in [(1,10,100),(2,10,100)]:
   m.ingest({'received_at':f'2026-10-09T17:00:0{t}+00:00','message':{'type':'ob_l1','ts':1791565200000000+t*1000000,'bp':str(100 if t==1 else 100.5),'bs':str(bq),'ap':'101','as':str(aq)}})
  s=m.snapshot(now=1791565203)
  self.assertTrue(s['ofi_vamp_disagreement'])
  self.assertTrue(s['vamp_inside_spread'])

 def test_500ms_incremental_flow_is_a_proxy_not_unmatched_volume(self):
  m=Monitor()
  m.ingest({'received_at':'2026-10-09T17:00:01+00:00','message':{'type':'ob_l1','ts':1791565201000000,'bp':'100','bs':'10','ap':'101','as':'10'}})
  for sec,px,qty in [(2,101,60),(2,100,10)]:
   m.ingest({'received_at':f'2026-10-09T17:00:0{sec}+00:00','message':{'type':'trades','ts':1791565200000000+sec*1000000+qty,'p':str(px),'s':str(qty)}})
  s=m.snapshot(now=1791565202.2)
  f=s['incremental_flow_500ms']
  self.assertEqual(f['window_ms'],500)
  self.assertEqual(f['signed_delta'],50)
  self.assertIn('not literal unmatched volume',f['interpretation'])
 def test_timestamp_unit_conversion(self):
  self.assertEqual(ts_seconds({'ts':1791565201000000}),1791565201)

if __name__=='__main__':unittest.main()
