from unified_probabilistic_scalper import UnifiedProbabilisticScalper

def test_probabilities_sum_to_one():
    f=UnifiedProbabilisticScalper().forecast({'imbalance':.4,'flow':.3,'momentum':.2})
    assert abs(f.p_up+f.p_down+f.p_flat-1)<1e-6

def test_missing_features_fail_safe():
    d=UnifiedProbabilisticScalper().decide({})
    assert d.action=='ABSTAIN'

def test_costs_are_subtracted():
    low=UnifiedProbabilisticScalper().decide({'imbalance':.1,'flow':.1,'momentum':.1,'structure':.1,'regime':.1,'liquidity':.1})
    assert low.expected_net_bps < 20

def test_no_execution_authority():
    assert not hasattr(UnifiedProbabilisticScalper,'submit_order')
