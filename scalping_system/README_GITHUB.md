# BTC Fisher / Delta Scalping System (research package)

This directory preserves the working-tree source for the BTC Fisher / Delta scalping research system alongside the existing Delta Pro application.

## Scope
- Strategy research, feature engineering, and validation scripts
- Delta public market-data collection and offline audit
- Paper trading, fill simulation, and read-only margin monitoring
- Execution readiness and risk-control research
- Dashboard source and automated tests

## Safety and data handling
- Research and paper trading only; this package does not authorize real orders.
- The frozen production `MonthlyFisher` configuration and production risk/execution controls must not be changed without explicit approval.
- `.env` files, API credentials, raw market snapshots, generated datasets, local databases, logs, model weights, caches, virtual environments, and Git history are excluded.
- Treat any live trading adapter as sensitive and verify all safety gates independently before use.

## Focused tests
Run from this directory:

```bash
python -m unittest research.test_delta_market_data_harvester_v1 research.test_delta_market_snapshot_audit_v1 research.test_delta_feature_dataset_v1 paper.test_margin_sentinel_readonly paper.test_delta_margin_sentinel_api
```

The latest focused validation for the new public data/feature and read-only margin components passed 36 tests on 2026-10-09. That is a code/test result, not evidence of positive trading expectancy.
