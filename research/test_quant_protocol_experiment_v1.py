import numpy as np
from research.quant_protocol_experiment_v1 import (
    block_bootstrap_ci, fit_logistic, prob_metrics, sigmoid, trade_metrics
)

def test_logistic_probability_is_finite_and_bounded():
    x = np.linspace(-0.02, 0.02, 200)
    y = (x > 0).astype(float)
    w, b, mu, sd = fit_logistic(x, y)
    p = sigmoid(w * ((x - mu) / sd) + b)
    assert np.isfinite(p).all()
    assert ((p >= 0) & (p <= 1)).all()
    assert p[-1] > p[0]

def test_probability_metrics_compare_to_known_base_rate():
    result = prob_metrics([0, 1, 0, 1], [0.5, 0.5, 0.5, 0.5])
    assert result["n"] == 4
    assert result["brier"] == 0.25
    assert abs(result["log_loss"] - 0.69314718056) < 1e-8

def test_trade_metrics_report_losses_and_drawdown():
    result = trade_metrics([2.0, -1.0, -3.0, 4.0])
    assert result["independent_trade_count"] == 4
    assert result["profit_factor"] == 1.5
    assert result["max_drawdown_bps"] == 4.0

def test_bootstrap_is_seeded_and_refuses_tiny_sample_ci():
    assert block_bootstrap_ci([1.0, -1.0])["low_95"] is None
    a = block_bootstrap_ci([float(i % 3 - 1) for i in range(30)])
    b = block_bootstrap_ci([float(i % 3 - 1) for i in range(30)])
    assert a == b
    assert a["low_95"] <= a["high_95"]
