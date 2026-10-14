# Quantitative Model Validation Protocol v1 — Research Only

This layer implements reusable validation primitives for the uploaded Quantitative Model Validation & Accuracy Enhancement Protocol. It is deliberately isolated from MonthlyFisher, the decision engine, live execution, credentials, and risk controls.

## Implemented
- Purged combinatorial cross-validation (CPCV-style) with label-horizon purge and embargo.
- Expanding walk-forward splits with chronological holdout separation.
- Probability quality (Brier score, log loss) and conformal interval coverage/width.
- Execution-cost sensitivity including configurable extra slippage ticks.
- Seeded moving-block return permutation test (default 10,000 permutations).
- Approximate trial-count-adjusted Sharpe diagnostic. It is not a formal DSR absent a complete trial ledger and explicit sampling assumptions.
- Synthetic order-book wall injection and downside interval-widening stress utilities. These are test fixtures, not spoof detection or NLP models.
- Unit tests for leakage boundaries, reproducibility, cost arithmetic, and stress-fixture isolation.

## Not implemented by this module
- Automated NLP news ingestion or real sentiment-shock classification.
- Full event-by-event Delta L2 replay, exchange queue-position/fill simulation, or latency calibration.
- A complete CQR model fit; this module evaluates supplied intervals only.
- Automatic model retraining, production promotion, or live order execution.

## Run
From the repository root:
```sh
.venv/bin/python -m pytest research/test_model_validation_protocol_v1.py -q
```

The functions accept arrays supplied by existing research workflows. Integrate one hypothesis at a time and retain the source dataset manifest, trial count, timestamp/sequence quality report, cost assumptions, and untouched chronological holdout with each result. Do not run on FAIL_CLOSED capture sessions.

## Promotion rule
This module never promotes a model. All outputs are research diagnostics. Live trading remains blocked pending data-integrity gates, independent reproduction, prospective shadow/paper validation, verified exchange contract/cost/fill assumptions, and explicit human approval.
