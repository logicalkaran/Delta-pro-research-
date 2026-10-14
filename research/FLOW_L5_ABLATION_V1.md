# Flow + L5 Imbalance Ablation v1

Research-only experiment comparing a signed-flow proxy (`delta30`) against the same model with five-level order-book imbalance (`imb5`) added. It uses saved labelled microstructure snapshots and does not alter the frozen MonthlyFisher strategy or execute orders.

## Reproduce
From repository root:
```sh
.venv/bin/python research/flow_l5_ablation_v1.py
.venv/bin/python -m pytest research/test_flow_l5_ablation_v1.py -q
```

Outputs to `data/processed/flow_l5_ablation_v1.json`. Existing reports are not overwritten.

## Method
- 60s, 120s and 300s targets.
- Rows must have freshness <=2s and valid timestamped target.
- Select non-overlapping label windows.
- Three expanding chronological test folds; train target windows must end before test start.
- Train-only scaling and logistic fit.
- Compare Brier/log-loss/accuracy and fixed probability threshold trade sensitivity at a placeholder 14 bps cost.

## Interpretation
A better Brier score is incremental forecast information, not necessarily a profitable strategy. The placeholder cost is not a verified fill model. The underlying feature file lacks session IDs for many rows, and saved imbalance is not an event-level historical book. Results are exploratory and cannot authorize production promotion. Validate session boundaries and raw tape provenance before treating any positive result as confirmatory.
