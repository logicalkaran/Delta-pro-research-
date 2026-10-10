import unittest
from research.cost_threshold_maker_shadow_v1 import BarrierConfig, first_touch_label, simulate_passive_quote

class TestBarrierLabels(unittest.TestCase):
    def test_target_first(self):
        x=first_touch_label(100,[{'ts':0,'mid':100},{'ts':1,'mid':100.21}],1)
        self.assertEqual(x['label'],1)
    def test_stop_first(self):
        x=first_touch_label(100,[{'ts':0,'mid':100},{'ts':1,'mid':99.89}],1)
        self.assertEqual(x['label'],-1)
    def test_abstain_when_no_barrier_and_complete(self):
        x=first_touch_label(100,[{'ts':0,'mid':100},{'ts':300,'mid':100.01}],1)
        self.assertEqual(x['label'],0); self.assertEqual(x['class'],'ABSTAIN_NO_BARRIER')
    def test_sampling_tolerance_accepts_near_horizon(self):
        x=first_touch_label(100,[{'ts':0,'mid':100},{'ts':299.2,'mid':100.01}],1)
        self.assertEqual(x['class'],'ABSTAIN_NO_BARRIER')
    def test_incomplete_path_abstains(self):
        x=first_touch_label(100,[{'ts':0,'mid':100},{'ts':30,'mid':100.01}],1)
        self.assertEqual(x['class'],'ABSTAIN_INCOMPLETE_PATH')
    def test_queue_expansion_aborts(self):
        x=simulate_passive_quote(side='LONG',best_bid=100,best_ask=100.01,queue_ahead_initial=100,queue_ahead_peak=126,fill_after_ms=100)
        self.assertEqual(x['status'],'CANCEL_QUEUE_HAZARD')
    def test_ttl_expiration(self):
        x=simulate_passive_quote(side='LONG',best_bid=100,best_ask=100.01,queue_ahead_initial=100,queue_ahead_peak=110,fill_after_ms=501)
        self.assertEqual(x['status'],'EXPIRED_UNFILLED')
    def test_costs_applied_without_free_spread_credit(self):
        x=simulate_passive_quote(side='LONG',best_bid=100,best_ask=100.01,queue_ahead_initial=100,queue_ahead_peak=110,fill_after_ms=200,markout_bps=20)
        self.assertAlmostEqual(x['net_markout_bps'],20-2.36-5.90-1.5)
        self.assertFalse(x['live_execution_enabled'])

if __name__=='__main__': unittest.main()
