# Cost-Threshold Barrier Research — 2026-10-10

**Decision: NO VALIDATED EDGE. Research/paper only; real orders disabled.**

## What changed

- Fixed the first-touch dataset builder's horizon-coverage check. The old strict check rejected ordinary asynchronous samples that ended just under 300 seconds, producing zero complete rows.
- Added an explicit 2-second sampling tolerance and a 3-second maximum inter-sample-gap guard. Windows crossing capture gaps are excluded rather than stitched across unrelated periods.
- Added a regression test for the sampling-tolerance case.

## Dataset result

Source: `data/processed/live_microstructure_features_v1.jsonl`
Output: `data/processed/cost_threshold_barrier_labels_v1.jsonl`

- Source rows accepted: 36,399
- Complete 300-second entry timestamps: 26,996
- Directional labels: 53,992 (long and short per entry timestamp)
- TARGET_FIRST: 2,090
- STOP_FIRST: 12,277
- ABSTAIN_NO_BARRIER: 39,625

These labels overlap heavily in time and are not independent trades. They are not an executed PnL backtest, do not establish fill probability, and cannot support a profitability claim.

## Chronological descriptive check

Using timestamp-grouped 60/20/20 chronological partitions and a 300-second purge around boundaries:

| Split | Directional labels | Unique entry timestamps | Target share among barrier touches |
|---|---:|---:|---:|
| Train | 31,826 | 15,910 | 18.49% |
| Validation | 9,658 | 4,828 | 6.05% |
| Test | 10,226 | 5,113 | 8.51% |

The target share deteriorates materially outside the training period. These are descriptive label counts, not strategy returns; overlapping labels and incomplete session identity limit inference.

## Cost hurdle

With a +20 bps target and -10 bps stop, ignoring timeout outcomes:

- At 9.76 bps assumed maker-entry/taker-exit fees plus adverse selection, the theoretical break-even target-first rate is about 65.9%.
- At the project's 11.8 bps taker baseline, it is about 72.7%.
- At the conservative 15.8 bps research cost assumption, it is 86.0%.

These are simplified hurdle calculations, not evidence that those costs or fills will be achieved. The observed target-first share among touched labels is far below these hurdles in validation and test. A filtered strategy could differ, but has not been demonstrated.

## Existing evidence and next gate

Existing project reports already show negative cost-adjusted holdout results; the latest production audit's aggregated paper metrics showed 6 completed trades, -9.24 bps average net, and PF 0.027. That sample is too small for reliable inference but clearly does not pass promotion gates.

Next experiment should be a pre-registered, purged walk-forward test of a small set of entry filters, with executable bid/ask outcomes, explicit timeout PnL, realistic fee/slippage scenarios, and session-level replication. Freeze thresholds before holdout evaluation. Do not train on overlapping samples as if independent, infer passive fills from mid-price paths, or promote any candidate unless net expectancy and PF remain positive across unseen sessions.

## Safety

No production Fisher or Decision Engine code was changed. No exchange orders were submitted. Live execution remains blocked.
## Follow-up filter screen — 2026-10-10 04:55 UTC

A reproducible, pre-defined screen was added at `research/cost_threshold_filter_screen_v1.py`; output is `data/processed/cost_threshold_filter_screen_v1.json`. Eight rules were evaluated: delta30, ret30, imbalance10, CVD slope, 2-of-4 and 3-of-4 confluence, pressure continuation, and absorption reversal. Entries are spaced by 300 seconds, and chronological split boundaries are purged by 300 seconds. No thresholds were optimized on the holdout.

At the 11.8 bps cost assumption, none of the eight rules was profitable on validation or test. Validation average net results ranged from -10.24 to -14.66 bps; test ranged from -10.21 to -12.63 bps. The best test average was still -10.21 bps (2-of-4 confluence), with PF 0.023. Selected samples were small (18–23 trades in test) and come from one capture period.

The same rules were also screened at 15.8 bps costs; results deteriorated further. No promotion candidate passed. These figures use fixed barrier outcomes and terminal mid-price returns for timeouts; they are not fill-based PnL and may understate execution friction. This experiment rejects these simple directional rules for the current sample; it does not prove all possible strategies fail.

Next research should prioritize capture quality and an independent multi-session dataset before another model search. Avoid adding complexity to explain a failed holdout, and keep all live execution blocked.
## Fresh-capture rerun — 2026-10-10 04:57 UTC

The microstructure feature tape is actively appending again. The latest row belongs to capture session `l2_5level_20261010_044532_a5c3f1` and reports state age about 0.025 seconds at inspection. The builder was rerun on this fresher tape:

- Source rows: 36,656
- Complete 300-second entry timestamps: 27,254
- Directional labels: 54,508
- Class counts: 2,090 target-first; 12,277 stop-first; 40,141 no barrier.

The eight-rule screen was rerun after rebuilding the labels. Status remains `NO_VALIDATED_EDGE`. At 11.8 bps assumed costs, validation average net ranged from -10.95 to -15.04 bps; test ranged from -9.59 to -13.00 bps. The least-negative test result was delta30/CVD at -9.59 bps, PF 0.024, with only 23 non-overlapping selected entries. That is still strongly negative and far below a usable sample size.

Freshness is improving, but this is still essentially one continuous capture session, not independent day/session replication. The source rows are quote/mid-price snapshots; the result does not establish passive queue fills or executable PnL. Keep research-only status.
