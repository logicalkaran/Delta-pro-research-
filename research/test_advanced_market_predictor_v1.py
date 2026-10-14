from advanced_market_predictor_v1 import (
    forecast, order_book_imbalance, pinball_loss,
)


def test_obi_top_levels_and_empty_book():
    assert order_book_imbalance({"buy": [[100, 3], [99, 1]], "sell": [[101, 2]]}, 2) == (1.0 / 3.0)
    assert order_book_imbalance({}, 5) is None


def test_forecast_is_paper_only_and_has_quantiles():
    candles = [{"close": 100 + i * 0.2} for i in range(150)]
    result = forecast(candles, horizon=5, calibration_errors=[0.1] * 30,
                      cost_bps=1, min_samples=50)
    assert result["status"] == "RESEARCH_ONLY"
    assert result["return_quantiles_pct"]["q10"] <= result["return_quantiles_pct"]["q50"]
    assert result["return_quantiles_pct"]["q50"] <= result["return_quantiles_pct"]["q90"]
    assert result["prediction_interval_pct"]["calibrated"] is True
    assert result["paper_only"] is True
    assert result["order_submission"] is False
    assert result["promotion_allowed"] is False


def test_insufficient_sample_never_emits_direction():
    candles = [{"close": 100 + i} for i in range(12)]
    result = forecast(candles, horizon=5, min_samples=100)
    assert result["status"] == "INSUFFICIENT_DATA"
    assert result["direction"] == "FLAT"


def test_unclosed_candle_is_ignored():
    candles = [{"close": 100 + i} for i in range(20)]
    candles.append({"close": 100000, "closed": False})
    result = forecast(candles, horizon=2, min_samples=1)
    assert result["current_price"] == candles[-2]["close"]


def test_pinball_loss():
    assert pinball_loss(10, 8, 0.9) == 1.8
    assert pinball_loss(8, 10, 0.1) == 1.8
