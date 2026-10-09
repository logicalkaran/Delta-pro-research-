import unittest
from research.execution_economics_synthesis_v1 import build_report, summarize
class EconomicsSynthesisTests(unittest.TestCase):
 def test_no_positive_holdout_blocks_promotion(self):
  data={'rows_loaded':100,'results':[{'split':'holdout','event':'A','horizon_s':60,'route':'MAKER','expected_net_per_signal_bps':-1.2},{'split':'holdout','event':'B','horizon_s':120,'route':'TAKER','expected_net_per_signal_bps':0.0}]}
  r=build_report({'toy':data})
  self.assertEqual(r['aggregate']['positive_net_holdout_results_across_studies'],0)
  self.assertIn('BLOCKED',r['aggregate']['promotion_decision'])
 def test_positive_candidate_counted(self):
  r=summarize('toy',{'results':[{'split':'holdout','route':'MAKER','event':'X','horizon_s':120,'expected_net_per_signal_bps':0.4}]})
  self.assertEqual(r['positive_net_holdout_count'],1)
  self.assertEqual(r['best_holdout']['expected_net_bps'],0.4)
 def test_missing_or_nonfinite_metrics_ignored(self):
  r=summarize('toy',{'results':[{'split':'holdout','expected_net_per_signal_bps':'nan'},{'split':'train','expected_net_per_signal_bps':5}]})
  self.assertEqual(r['holdout_result_count'],0)
  self.assertIsNone(r['best_holdout'])
 def test_real_orders_always_false(self):
  self.assertFalse(build_report({})['real_orders'])
if __name__=='__main__': unittest.main()
