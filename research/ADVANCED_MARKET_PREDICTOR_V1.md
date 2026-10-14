# Advanced Market Predictor v1 — research milestone

Status: implemented, isolated, paper-only. No production routing or order execution integration.

## Implemented

- Completed-candle validation (bars marked `closed: false` are ignored).
- Empirical horizon-return q10/q50/q90 quantiles.
- Optional split-conformal widening from caller-supplied, chronological calibration residuals.
- Empirical up/down frequencies, recent volatility and momentum.
- Top-N order-book imbalance (OBI) as a confirmation input.
- Conservative selective UP/DOWN/FLAT output using minimum sample count, a cost assumption and OBI conflict veto.
- Pinball loss helper for out-of-sample quantile scoring.
- Explicit paper-only flags and limitations in each forecast.

## Use from the existing repository

```python
from research.advanced_market_predictor_v1 import forecast

# candles must be ordered oldest to newest and contain completed OHLCV bars.
# Calibration errors are independent chronological residuals in return percentage
# points (e.g. 0.12 means 0.12%, not 12 bps).
result = forecast(
    candles=completed_candles,
    order_book={"buy": [[bid_price, bid_size], ...],
                "sell": [[ask_price, ask_size], ...]},
    horizon=5,
    calibration_errors=held_out_calibration_errors,
    cost_bps=12.0,
    min_samples=100,
)
print(result)
```

Run its regression tests:

```sh
.venv/bin/python -m pytest -q research/test_advanced_market_predictor_v1.py
```

## Important limits

This is an empirical statistical baseline, not the PDF's proposed trained Mamba/Temporal Fusion Transformer. It does not claim that 80% interval coverage is guaranteed: conformal coverage depends on calibration design and exchangeability, which overlapping financial returns can violate. Direction frequencies are not calibrated future probabilities. Use purged chronological walk-forward tests and real venue-specific fees/slippage before judging edge.

No new packages were installed. The module is not connected to production signals, live execution, account APIs, or risk controls. MonthlyFisher and signal production files were not edited. Keep live orders disabled.
