# Qwen BTC research specialization

This is a prompt plus retrieval and supervised research-example layer. It does not train or modify Qwen weights and has no imports from strategy, risk, or execution modules.

## Artifacts

- `SYSTEM_PROMPT.md`: analyst role, uncertainty standards, and hard no-order/no-risk boundary.
- `knowledge.json`: sourced facts, explicitly labeled hypotheses, and failure examples.
- `training.jsonl`: compact point-in-time input/target examples. It contains the latest 681 feature snapshots and latest 387 fully labeled observations from the existing bounded tapes (1,068 records total). Current source tapes can contain more rows; the builder caps to the stated research cohort.
- `layer.py`: cohort builder and retrieval/context helpers.
- `test_layer.py`: leakage, cohort, and context tests.

Each supervised row has `input.features` and a separate `target.horizons[*].move_bps`. Future prices and future timestamps are omitted. Targets are outcomes for offline evaluation or supervised data handling only; never concatenate targets into inference prompts.

## Use at inference

```python
from research.qwen_specialization.layer import build_context
context = build_context(now_ts=current_epoch_seconds)
prompt = open("research/qwen_specialization/SYSTEM_PROMPT.md").read()
# Supply prompt + JSON-serialized context to Qwen. Keep knowledge.json as retrieved
# evidence, and do not pass training.jsonl targets into an inference request.
```

The context includes the current microstructure snapshot, up to ten recent feature-only tape rows, and trailing 5m/15m/1h summaries aggregated from the existing 1m candle file. A timeframe is marked not ready unless its complete window exists. If data are stale or context conflicts, the persona directs Qwen to abstain. The builder has no order, leverage, risk, or production-strategy interface.

Regenerate the static cohort with `python -m research.qwen_specialization.layer`. Run checks with `python -m unittest research.qwen_specialization.test_layer -v`.
