# Regime-conditioned microstructure framework — implementation notes

This extension implements the four modules named in *System Implementation & AI Handoff Specifications* and adds a research-only SQLite WAL paper ledger.

- `research/event_features.py`: validated five-level book events, exponential-decay MLOFI, and strictly increasing exchange event timestamps. Identical book states are rejected; local polling timestamps are not accepted as exchange event time.
- `research/queue_simulator.py`: deterministic passive queue, proportional queue thinning when displayed queue observations are supplied, and fill only on first passage by the correct aggressive trade direction. Touch alone never fills; expiry cancels the simulated child.
- `research/adverse_selection.py`: side-signed post-fill mid/microprice markout and volume-weighted aggregation. Missing volume remains missing, not zero.
- `research/model_evaluator.py`: Brier score and finite-sample Murphy reliability/resolution/uncertainty decomposition. The decomposition is bin-estimated; inspect residual and sample counts.
- `research/microstructure_paper_ledger.py`: SQLite WAL paper-only parents/children/events and use of `risk.orchestration_oracle.evaluate`. Missing/incomplete account state fails closed. No exchange client, HTTP, websocket, or live-order call is imported.

## Safety and limits

The paper ledger refuses to silently accept scaled quantities as though they were the original requested intent. It records only a fully approved paper parent. It never submits live orders. Risk evaluation uses the existing oracle's 5% adverse shock and 20% stress headroom defaults, but those defaults are not proof of exchange-specific liquidation behavior. The requested 0.02% maker rebate in the PDF is not assumed: verify current Delta account-specific fees/rebates before any economic evaluation. The 0.05% taker fee is likewise a model input to be verified, not hard-coded as guaranteed truth.

The MLOFI function requires a caller-supplied exchange event timestamp and true L5 book state mutations. The current sampled JSON state file is not a substitute for exchange-native incremental events. Queue cancellation thinning is only a proxy unless full order-level queue priority and trade/depth updates are available. No production strategy or live execution files were changed by this addition.

## Run focused tests

```sh
python -m pytest -q research/test_regime_microstructure_framework.py research/test_microstructure_paper_ledger.py
```
