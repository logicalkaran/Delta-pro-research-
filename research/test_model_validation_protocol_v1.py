import numpy as np
import pytest
from research.model_validation_protocol_v1 import (
    purged_combinatorial_splits, walk_forward_splits, probability_metrics,
    conformal_interval_metrics, execution_cost_sensitivity,
    block_permutation_test, deflated_sharpe_diagnostic, spoof_orderbook,
    shock_conformal_lower_band,
)

def test_cpcv_purges_train_labels_and_yields_multiple_splits():
    splits=list(purged_combinatorial_splits(120,n_groups=6,n_test_groups=2,label_horizon=3,embargo=2))
    assert len(splits)>1
    for train,test in splits:
        assert not set(train)&set(test)
        for t in test:
            assert not np.any((train <= t+3) & (train >= t-4))

def test_walk_forward_is_chronological_and_purged():
    for train,test in walk_forward_splits(200,n_splits=4,label_horizon=5,embargo=2):
        assert train.max()+5+2 < test.min()

def test_metrics_and_costs():
    assert probability_metrics([0,1],[.1,.9])["brier"] == pytest.approx(.01)
    assert conformal_interval_metrics([0,1],[-1,0],[1,2],.9)["empirical_coverage"] == 1
    assert execution_cost_sensitivity([10,-2],5)["mean_net_bps"] == pytest.approx(-1.0)

def test_permutation_reproducible_and_finite():
    s=np.tile([1.,-1.,0.,1.,-1.],10)
    r=np.tile([5.,-4.,0.,3.,-2.],10)
    a=block_permutation_test(s,r,2,n_permutations=100,block_size=2,seed=7)
    b=block_permutation_test(s,r,2,n_permutations=100,block_size=2,seed=7)
    assert a==b and 0<a["one_sided_p_value"]<=1

def test_dsr_diagnostic_refuses_small_sample():
    assert deflated_sharpe_diagnostic([1.,-1.]*5)["status"]=="INCONCLUSIVE"
    result=deflated_sharpe_diagnostic(np.random.default_rng(1).normal(.1,1,100),trials=20)
    assert 0<=result["probability_sharpe_exceeds_benchmark_approx"]<=1

def test_spoof_and_sentiment_interval_stress_do_not_mutate_inputs():
    book=[[100.,2.],[99.,3.]]
    assert spoof_orderbook(book,multiplier=10)[0][1]==20
    assert book[0][1]==2
    lo,hi=shock_conformal_lower_band([-2.,-2.],[2.,2.],[True,False],3.)
    assert lo==[-5.,-2.] and hi==[2.,2.]
