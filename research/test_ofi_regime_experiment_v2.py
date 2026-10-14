import importlib.util
from pathlib import Path
import numpy as np
P=Path(__file__).with_name('ofi_regime_experiment_v2.py')
S=importlib.util.spec_from_file_location('ofi_v2',P); M=importlib.util.module_from_spec(S); S.loader.exec_module(M)

def test_delta_fee_assumptions_are_charges_not_rebate():
    assert round(M.MAKER_FEE_BPS,3)==2.36
    assert round(M.TAKER_FEE_BPS,3)==5.9
    assert M.MAKER_RATE>0

def test_risk_oracle_fails_closed_without_account_state():
    r=M.risk_fixture(80000.0,0.001)
    assert r['verdict']=='BLOCKED_MISSING_AUTHORITATIVE_ACCOUNT_STATE'
    assert r['simulated_execution_allowed'] is False
    assert r['adverse_shock_fraction']==0.05

def test_probability_metrics_are_finite():
    r=M.pmetrics([0,1,0,1],[.1,.8,.4,.7])
    assert 0<=r['brier']<=1 and r['log_loss']>0

def test_hmm_posterior_sums_to_one():
    X=np.column_stack([np.linspace(-1,1,60),np.sin(np.arange(60)),np.cos(np.arange(60))])
    model=M.fit_hmm(X,K=3,iterations=2)
    p=M.hmm_filter(model,X)
    assert p.shape==(60,3)
    assert np.allclose(p.sum(axis=1),1.0,atol=1e-6)
