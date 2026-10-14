# Historical BTC Dataset Collection & Deterministic Backtest Plan
Date: 2026-10-11
Project: ~/btc_fisher_trader
Mode: offline research / paper-only; no real orders

## Scope and safety invariants

- Window: UTC [2024-10-11T00:00:00Z, 2026-10-11T00:00:00Z). Exclude any incomplete current 1h candle.
- Resolution: 1h candles for both venues. This is a strategy-level dataset, not a substitute for tick-level execution data.
- Venues: Delta Exchange India BTCUSD product as confirmed by product metadata; Binance USDⓈ-M BTCUSDT perpetual. Keep venue-native datasets and contract units separate.
- Preserve frozen MonthlyFisher in strategy/fisher.py: HL2, length 10, alpha 0.33, beta 0.67. No edits to production strategy, decision engine, execution, live risk, API credentials, or runtime state.
- All requests must be public/read-only market-data endpoints. No order, account, leverage, margin, transfer, or private endpoints. Do not enable live execution.
- No large dataset download, dependency installation, or full historical L2 acquisition until storage and expected-size checks have been reviewed and explicitly approved.
- Repository currently has extensive uncommitted modifications/untracked files. Do not reset, clean, checkout, stash, or overwrite any of them. This plan is a new research document only.

## Existing project assets to reuse

- research/candle_history_sync_v1.py: short-window Delta cache only; not a 2-year collector.
- research/delta_market_data_harvester_v1.py: Delta public data harvester, but currently only bounded windows and must not be mistaken for a 2-year backfill.
- research/deterministic_replay_v1.py: event-time replay primitives. It intentionally rejects missing local receive times and does not by itself implement a candle backtest.
- strategy/fisher.py: frozen MonthlyFisher implementation.
- Existing cross-venue collectors, integrity audits, order-book validators, and replay tests should be inspected and reused rather than duplicated.
- Prior capture finding: a session reported sequence_gaps=1 despite raw audit passing. Historical/event research must fail closed on unexplained sequence gaps and must not silently accept the affected session.

## Data plan

### A. Required compact baseline: hourly candles

1. Delta Exchange India:
   - Confirm BTCUSD product metadata and contract type/settlement/quote conventions from the public products endpoint before collection.
   - Fetch GET /v2/history/candles with resolution=1h, symbol=BTCUSD, Unix-second start/end.
   - Endpoint maximum is 2,000 candles per response; use bounded, non-overlapping chunks (e.g. 1,800 hourly bars per request) with explicit boundary rules.
   - Also investigate hourly MARK:BTCUSD, FUNDING:BTCUSD, and OI:BTCUSD series. Validate each series independently; absence or partial coverage is recorded, not fabricated.
2. Binance USDⓈ-M:
   - Fetch BTCUSDT 1h klines from the official futures market-data endpoint or official Binance Vision monthly archives.
   - Use monthly archive files when available; otherwise paginate requests within documented limits. Verify archive checksums when supplied.
   - Collect funding-rate history and mark-price klines where supported/available. Open-interest history may have shorter retention; report actual coverage rather than implying two years.
3. Store source-native raw responses/files before normalization. Normalized records must retain venue, symbol, product/contract type, interval, UTC open time, close time, OHLC, volume fields with original units, source path/request metadata, retrieval time, and raw-file SHA-256.
4. Canonical hourly bar convention: UTC open-time aligned to exact hour. For a bar at t, its close is not available until the bar closes. Generate a strategy signal only after close confirmation; earliest modeled entry is the next bar/open or a later quote, never the same bar's close with hindsight.

### B. Microstructure data: separate coverage audit before any bulk download

- Binance historical futures order-book data is not assumed to be freely or fully available for the entire two-year window. Official historical L2 access has separate eligibility/access requirements and documented gaps. First obtain a catalogue/coverage/size estimate; do not start bulk download.
- Delta's current public L2 endpoint is a current snapshot, not proof of two-year historical order-book availability. Historical snapshots/deltas must be sourced from existing local raw captures or a confirmed exchange archive/vendor.
- Use existing local raw JSONL captures where present. Inventory date span, record count, event types, sequence gaps, timestamp fields, and hashes before selecting sessions.
- Keep hourly candle backtests independent of L2 availability. Mark microstructure periods as unavailable if reliable historical L2 does not exist. Never synthesize historical order books from candles.
- For any acquired L2 stream, validate snapshot/delta synchronization, sequence continuity, bid/ask ordering, duplicate/out-of-order events, timestamp units, exchange/local clock alignment, and staleness. A gap without a verified resnapshot makes the affected segment unusable for book-dependent replay.

## Storage layout proposal (create only after size/storage approval)

- data/raw/historical_btc/manifest.json
- data/raw/historical_btc/delta_india/BTCUSD/1h/...
- data/raw/historical_btc/binance_usdm/BTCUSDT/1h/...
- data/raw/historical_btc/{venue}/funding/...
- data/raw/historical_btc/{venue}/mark_price/...
- data/raw/historical_btc/{venue}/open_interest/...
- data/raw/historical_btc/{venue}/trades/...
- data/raw/historical_btc/{venue}/orderbook/...
- data/processed/historical_btc/quality_report.json
- data/processed/historical_btc/normalized_hourly.parquet (only if an already-installed compatible writer exists; otherwise CSV/JSONL, no dependency installation without approval)
- data/processed/historical_btc/backtest_runs/<run_id>/...

Never overwrite live files such as data/live_candles.json, data/runtime_state.json, or live-market state files. Research outputs stay under the historical_btc namespace.

## Quality gates before any backtest

Fail closed or quarantine the affected series if any critical check fails:

1. Schema: numeric finite OHLCV; positive prices; volume nonnegative; high >= max(open, close, low); low <= min(open, close, high).
2. Identity: symbol, venue, product/contract type, settlement/quote unit and interval match the manifest.
3. Time: UTC epoch unit is explicit; timestamps align to hourly boundaries; chronological sort; duplicate timestamps are resolved only by a documented deterministic rule; no silent timezone conversion.
4. Coverage: expected count is approximately 17,520 bars for a complete two-year hourly window, minus explicitly documented partial endpoints/listing gaps. Report exact missing intervals and duplicate counts; do not fill missing OHLC with forward-fill.
5. Completeness: exclude currently open candle and any bar that fails closed-bar checks. Detect suspicious flatlined/zero-volume periods and extreme outliers for review, not automatic deletion.
6. Cross-source integrity: compare timestamps, price basis, volume units, mark/index/last price semantics. Do not expect Delta BTCUSD contract prices/volumes to equal Binance BTCUSDT values. Differences must be explained by contract design, basis, and market conditions.
7. Provenance: verify archive checksums where provided; compute local SHA-256; manifest records source URL/endpoint, request bounds, fetch time, software version, row counts, first/last timestamps, and hash.
8. Existing capture gates: any book data with unresolved sequence gaps, clock misalignment, stale state, or failed integrity audit is excluded from book-dependent experiments.

Quality report status values: PASS, PASS_WITH_GAPS (only if gaps are explicitly quantified and excluded from affected tests), or FAIL_CLOSED. No backtest runs on FAIL_CLOSED data.

## Deterministic backtest protocol

1. Reproduce the frozen Fisher output on a small known fixture before running the large dataset. Record a source hash of strategy/fisher.py and its configured parameters.
2. Sort closed candles by (venue, symbol, open_time); reject duplicates unless the manifest's deterministic resolution rule applies.
3. Feed candles sequentially. Do not compute indicators from future rows. Warm up at least the indicator lookback; do not score warm-up rows.
4. Signal timing: calculate after candle close; model order entry only at the next available executable price. If only OHLC is available, explicitly label the fill model as coarse and do not claim realistic intrabar execution.
5. Separate venue backtests. A cross-venue signal may use only data available by decision time, with explicit timestamps and staleness limits. Never splice venue bars into one synthetic series.
6. Apply point-in-time fee schedule and funding where reliable data exists. If historical fee tier is unknown, use declared conservative scenarios. Include spread, slippage and latency sensitivity. Do not assume maker fills from candle touches.
7. Position sizing and risk limits remain unchanged and are loaded read-only. This study must not modify live risk settings. Test flat/no-trade and zero-edge baselines as sanity checks.
8. Split chronologically: initial 60% development, next 20% validation, final 20% untouched test. Add rolling/walk-forward evaluation within development/validation; purge overlapping labels/trades at split boundaries where applicable. Do not tune on final test.
9. Report net returns after costs, trade count, expectancy, profit factor, maximum drawdown, exposure, turnover, win/loss distribution, regime breakdown, and confidence intervals or bootstrap uncertainty. Include baseline comparison and parameter-lock confirmation.
10. Deterministic reproducibility: fixed config, stable sort, deterministic seeds where stochastic procedures exist, input hashes, code commit/status snapshot, dependency/runtime versions, and output hashes. Re-running on identical inputs/config must reproduce signals and metrics within declared numeric tolerances.
11. Do not promote to paper/live or alter production strategy based solely on this research. Any future promotion requires separate approval and independent validation.

## Execution phases and stop conditions

Phase 0 — Read-only preflight (no downloads): inspect available storage, existing raw-data inventory, product metadata, installed libraries, repository status, and source/test compatibility. Record existing uncommitted changes; do not touch them.

Phase 1 — Source coverage probe (small bounded requests only): verify symbol/product identifiers, response schema, supported series, hourly coverage limits, archive availability/checksum convention, and L2 historical availability. Save only compact probe metadata.

Phase 2 — Size estimate and approval: calculate expected baseline volume and disk requirement from measured sample sizes plus temporary/extraction overhead. Ask for explicit approval before downloading the full two-year set or any large L2 archive.

Phase 3 — Backfill and normalize: chunked/restartable retrieval, atomic writes, idempotent resume, bounded retries/backoff, per-chunk hashes, no duplicate boundary bars. No changes to production or live files.

Phase 4 — Quality audit: generate manifest and quality report. Do not proceed to backtest unless critical gates pass.

Phase 5 — Offline deterministic evaluation: run frozen strategy only against approved data; store reports under research output directory; no execution routes.

Phase 6 — Independent reproduction: rerun with identical inputs, compare hashes/signals/metrics, and have a separate audit review leakage, fees, fill assumptions, and missing-data exclusions.

## Acceptance criteria

- No production/live/risk/credential files modified.
- No order or account mutation endpoints called.
- No large downloads or new dependencies before explicit approval.
- Both venues' hourly series have source provenance and a quality report; all gaps and data-basis differences are quantified.
- Book-dependent conclusions use only validated historical L2 periods and explicitly state coverage limitations.
- Frozen MonthlyFisher code/parameters remain unchanged.
- Final report is deterministic, reproducible, cost-aware, out-of-sample, and clearly distinguishes historical predictive performance from evidence of future profitability.


## Pre-registered structural hypothesis protocol (longer-horizon features)

Research objective: identify reproducible conditional return/liquidity asymmetries, not forecast a point price. Keep this study separate from the frozen MonthlyFisher baseline. No hypothesis is considered accepted from in-sample performance alone.

### Candidate structural hypotheses (test separately; do not combine until each is evaluated)

H1 — Funding/carry extreme:
- Mechanism: persistently extreme positive or negative perpetual funding may proxy crowded positioning and create conditional forward-return or reversal asymmetry.
- Feature: funding rate known at decision time; use the last published/settled rate and its trailing 7d/30d robust z-score or percentile. Never backfill a funding observation before its publication time.
- Null: H0: net mean excess return for the pre-defined strategy conditional on the funding state is <= 0.
- Alternative: H1: net mean excess return is > 0 on the untouched test set, with a pre-defined minimum economically meaningful effect after costs.
- Caveat: funding may be a carry payment rather than a directional signal. Test carry and directional returns separately; do not conflate them.

H2 — Volatility-regime dependence:
- Mechanism: trend/reversal effects and transaction costs vary across volatility regimes.
- Feature: lagged realized volatility from closed hourly returns (e.g. trailing 24h/7d), computed only with bars finalized by decision time; define regime thresholds using training data only.
- Null: conditional net expectancy does not improve out of sample versus unconditional baseline after controlling for costs and exposure.
- Alternative: pre-defined regime-conditioned policy improves out-of-sample net expectancy and/or downside risk by the pre-registered minimum.
- Report each regime's sample count and uncertainty; merge or mark sparse regimes inconclusive rather than tuning thresholds post hoc.

H3 — Funding × volatility interaction:
- Mechanism: crowded carry positioning may behave differently in high-volatility/liquidation-prone periods.
- Test only after H1 and H2 are reported independently. Pre-register a small, fixed interaction set; no unrestricted grid search.
- Null: interaction contribution to out-of-sample net expectancy is <= 0 after multiplicity correction.
- Alternative: positive incremental net edge survives the final holdout and correction for all attempted variants.

H4 — Liquidity/volatility friction interaction (only where reliable historical book/trade coverage exists):
- Mechanism: apparent returns can be offset by spread widening, market impact, adverse selection, and queue position during stress.
- Use only timestamp-validated L2/trade data; no synthetic historical book reconstruction from OHLC candles.
- Null: the apparent signal has no positive net edge after conservative execution simulation.
- If book history is unavailable for a date range, mark this hypothesis untested for that range.

### Pre-registration and evaluation metrics

Before any full run, write a dated, immutable experiment manifest containing hypothesis ID, exact feature formulas and lookbacks, observation/decision timestamps, signal/entry/exit rules, target horizon, universe/contract, fees and funding treatment, exclusion rules, train/validation/test dates, embargo duration, metrics, minimum effect size, random seed where applicable, and the number of attempted variants. Hash the manifest and source files.

Primary metric: net mean excess return per trade/period against a declared benchmark, with confidence interval. Test H0: mean net excess return <= 0 using a one-sided test selected before inspection. Use block bootstrap or another dependence-aware method for serially correlated returns; report sample size and uncertainty.

Secondary metrics, fixed before testing:
- Sortino ratio with explicitly stated target return and sampling frequency.
- Maximum drawdown and maximum drawdown duration.
- Net expectancy, profit factor, turnover, exposure, downside tail loss and trade count.
- Regime-conditional performance and edge decay across walk-forward folds.
- Costs as a fraction of gross edge and sensitivity under conservative fee/slippage scenarios.
- Calibration metrics only if a probability forecast is explicitly produced; otherwise do not label the output a calibrated probability.

Do not choose the winning metric after observing results. Report all pre-registered metrics, including negative results.

### Leakage, point-in-time controls and cross-validation

- Hourly feature at decision time t may use only completed bars and external observations whose publication/receipt time <= t. Entries occur no earlier than the next executable opportunity.
- Funding records require both effective/settlement time and known/available time where available. If historical publication timestamps are unavailable, use a conservative availability assumption and document it.
- Use expanding or rolling walk-forward evaluation. Do not use random k-fold splitting for the primary time-series result.
- For any labels that span future returns over horizon h, purge training samples whose label windows overlap the test interval. Apply an embargo at least as long as the maximum label horizon and any pre-registered overlap/latency buffer. State exact intervals.
- Keep the final chronological holdout untouched until hypotheses, thresholds, and cost assumptions are locked. No re-tuning after viewing holdout results.
- Survivorship control: this study targets BTC contracts, not a rotating multi-asset universe, so equity-style bankrupt/delisted-asset survivorship bias is not directly applicable to the single-BTC series. Still track contract listings, migrations, symbol/contract-spec changes, venue outages, and periods where the instrument was unavailable; do not silently splice incompatible contracts.

### Multiple testing and reporting discipline

- Maintain a trial ledger of every tested hypothesis, feature, threshold, horizon, cost scenario and model variant, including abandoned/failed runs.
- Apply Deflated Sharpe Ratio (DSR) when Sharpe-based comparisons and trial-count assumptions are valid; record assumptions and effective number of independent trials. Use a pre-selected FWER procedure (for example Holm-Bonferroni) for families of confirmatory hypothesis tests. Do not claim DSR/FWER correction if the trial ledger is incomplete.
- Treat feature selection and regime-threshold fitting as training-only operations. Validation data may be used only according to the pre-registration. Final holdout is evaluated once after lock.
- Report effect size, uncertainty interval, corrected and uncorrected results, number of trials, and failed hypotheses. Statistical significance without economically meaningful net edge is a rejection for deployment purposes.
- Do not infer future profitability from a positive backtest; require independent reproduction and prospective paper/shadow validation before any promotion review.

### Research acceptance gate

A hypothesis is classified as:
- REJECTED: negative or economically immaterial net edge, leakage, failed integrity, or edge erased by realistic costs.
- INCONCLUSIVE: insufficient independent observations, inadequate point-in-time feature timestamps, sparse regime coverage, or unavailable reliable execution data.
- PROVISIONAL: pre-registered net edge survives the locked out-of-sample test and multiplicity controls, but still requires independent reproduction and prospective paper validation.
- VALIDATED_FOR_PAPER_REVIEW: all prior checks pass, independent reproduction agrees, and prospective shadow/paper results are consistent; this status never authorizes live trading by itself.


## Phase 0/1 read-only preflight results — 2026-10-11

Status: **coverage probe complete; bulk collection not started**. Probe requests used public GET endpoints with small time windows and bounded response reads. Responses were not written to disk.

- Device storage at probe time: 219 GB total, 182 GB used, 37 GB available (84% used). Existing `data/raw` and `data/processed` already contain research captures; they are short sessions, not two years of L2 history.
- Frozen strategy integrity: `strategy/fisher.py` SHA-256 `969f25924c69fd04d6d9378c7ca345f8ef6140e853f6448402143248781e46d3`; file remains unchanged. Plan SHA-256 before this appended probe note was `49ab928f8a2c4902bff730b2abe7e70bcd03571e48b3d789fc8f44749ce2196d`.
- Existing targeted regression checks: `16 passed` for `test_fisher_reproduction.py`, `research/test_deterministic_replay_v1.py`, and `research/test_candle_history_sync_v1.py`.
- Delta Exchange India `BTCUSD` 1h candle query succeeded for a 24-hour historical sample around 2024-10-15 UTC and for a recent sample. The historical query returned 25 rows for a 24-hour inclusive window, with rows descending by timestamp; ingestion must sort and deduplicate and use explicit half-open expected intervals.
- Delta `MARK:BTCUSD`, `FUNDING:BTCUSD`, and `OI:BTCUSD` 1h history queries each returned sample rows for the same old period. Funding sample values were `0.01`; units/scale and exact funding event semantics must be validated against venue documentation before any economic interpretation. Mark and OI rows also came back newest-first and require canonicalization.
- Binance USDⓈ-M `BTCUSDT` metadata identifies a `PERPETUAL`, status `TRADING`, base BTC, quote/margin USDT. 1h klines and funding-rate history both returned a historical 2024-10-15 sample. Current 1h open-interest history query succeeded, but the equivalent old-period query returned HTTP 400; record this as an observed coverage/access limitation, not proof of a specific retention rule. Do not infer two-year OI coverage.
- Metadata caution: broad Delta `/v2/products` response exceeded the bounded 2.5 MB probe read, so the probe deliberately did not attempt to materialize the entire payload. Follow up with a safe targeted metadata request or bounded streaming parse before accepting contract metadata.
- Historical order book: the existing Delta harvester accesses `/v2/l2orderbook/{symbol}` for a current snapshot only. Existing local L2 captures are short sessions. No two-year historical L2 source was verified in this probe; do not treat snapshots or reconstructed books as historical depth.

### Gate decision after probe

**PASS for proceeding to a metadata/coverage manifest and size estimate; NOT YET PASS for bulk backfill.** Before downloading, resolve Delta product/contract metadata and units, test exact hourly range boundaries and page/chunk behavior, document Binance OI history limits, verify funding timestamps and scale, estimate raw and derived storage, and request explicit approval for the planned data volume. No bulk historical download, new dependency, production code edit, risk-setting change, credential access, or live order action occurred in this phase.


### Targeted Delta metadata follow-up

The targeted public endpoint `/v2/products/BTCUSD` succeeded, avoiding the oversized exchange-wide product response. It identifies product ID 27, symbol `BTCUSD`, contract type `perpetual_futures`, state `live`, BTC underlying, USD quote and settlement, contract value `0.001 BTC`, tick size `0.5`, maker commission `0.0002`, and taker commission `0.0005` in the returned metadata. These fields must be preserved with collection-time provenance and verified against current venue documentation before modeling costs/units. `/v2/l2orderbook/BTCUSD` returned a current snapshot with `buy`, `sell`, and `last_updated_at`; it is not a historical depth endpoint and cannot satisfy two-year L2 coverage by itself.


## Next-stage decision: evidence-first edge research — 2026-10-11

### Existing evidence reviewed (no reports overwritten)

The repository already contains a hypothesis registry/evaluator, funding carry calculator, depth/toxicity feature tape, purged walk-forward utility, OFI regime experiment, and cost/queue research. Reuse these before adding parallel frameworks.

- Re-ran `research/prediction_hypothesis_evaluator_v1.py` in memory against its existing 41,320-row `strategy_forward_tournament_v1.jsonl`; output was captured in memory only and no existing report was replaced. It assumes 12 bps costs and all six evaluated cohorts were negative on average: flow-price confirmation -11.36 bps (n=27); absorption failure -12.55 bps (n=240); liquidity sweep/reclaim -12.15 bps (n=47); regime-conditioned flow -12.33 bps (n=433); flow divergence -11.12 bps (n=25); order-book persistence proxy -12.28 bps (n=403). Most cohorts have small positive-return counts and/or small samples; these results are reject/inconclusive for edge claims, not proof that the underlying mechanisms never work. Note: the evaluator's `after_additional_cost_bps` applies an additional 12 bps deduction on top of the recorded `net_return_pct`, so do not confuse that field with its `avg_net_bps`.
- Existing `MOMENTUM_1M_TO_5M_V1` report decision is REJECT; pooled 64 selected trades show mean net -11.27 bps and a block-bootstrap 95% interval [-14.32, -7.50] bps under that experiment's assumptions.
- Existing `ORDER_FLOW_CONFIRMATION_5S_V1` decision is REJECT; 130 selected independent trades show mean net -13.91 bps under placeholder costs. The report explicitly lacks a full exchange event stream and queue-aware fills.
- Existing `OFI_REGIME_EXPERIMENT_V2` decision is NEED_MORE_DATA. Fold Brier improvements change sign (+0.0088, -0.0150, -0.0013); multi-level historical OFI and queue/fill labels are missing, so no passive-maker EV is estimable.
- Existing cross-venue audit for the 2026-10-10 session reports PASS on its limited checks (Binance depth continuity checks 5,843 with zero gaps; Delta L2 1,196 rows with no backwards/missing timestamps), but a different large 2026-10-09 capture recheck is FAIL_CLOSED because sequence continuity is unverifiable and there are timestamp duplicates/out-of-order events and aggregate-trade ID gaps. Keep the failed capture excluded from confirmatory analysis.
- Focused regression tests passed: 51 passed across funding carry, depth/toxicity features, OFI regime, quant protocol, cost filters, maker shadow, queue depletion, deterministic replay, and Fisher reproduction.

These existing reports appear to describe short recent capture windows, not the requested two-year sample. They are diagnostics for prioritizing research and cannot substantiate a long-horizon edge claim.

### Priority order for the next advanced research stage

1. **Data/label correctness gate:** build a manifest of every source file and UTC coverage; run schema, timestamp, duplicate, sequence, venue/contract identity, and closed-candle checks. Exclude `FAIL_CLOSED` captures from confirmatory tests. No backfill until its size and source coverage are approved.
2. **Funding hypothesis (H1) on hourly candles:** test lagged funding percentile/extremes and sign changes as predictors of next 8h/24h excess return and/or carry separately. Use only rates known by the decision timestamp; separate directional returns from funding cashflows; include actual venue-specific settlement timing, fees, basis and conservative slippage. Compare against unconditional and volatility-only baselines. No arbitrary threshold sweep without trial ledger.
3. **Volatility regime hypothesis (H2):** calculate realized volatility from completed bars only, with regime thresholds estimated on training data only. Test whether the frozen Fisher signal's *incremental* net expectancy and drawdown profile differ across regimes versus the same unconditional signal. Avoid retuning Fisher parameters; treat the strategy as frozen.
4. **Interaction hypothesis (H3):** only if H1 or H2 independently survives validation, test one pre-registered funding × volatility interaction against the additive/no-interaction baseline. Correct for the full set of attempted tests and report negative variants.
5. **Historical L2 hypothesis (H4):** request/verify Binance data-service eligibility and exact date coverage before requesting files. Official repository describes T_DEPTH as tick-by-tick L2 with gaps, S_DEPTH as roughly 1-second/20-level BTCUSDT snapshots with some missing data, and T_DEPTH_BACKFILL as a beta feed that stopped producing in mid-2021. Use only source ranges actually supplied and pass sequence/continuity checks. For Delta, retain live WebSocket updates prospectively; current REST snapshots are not an archive. Do not assume two years of full-depth history exists.
6. **Execution-aware test:** evaluate book imbalance/OFI, spread, depth, depletion and replenishment only where synchronized raw events support them. Compare incremental predictive value against price/funding/volatility-only baselines. Model latency, taker fees, maker queue position, non-fill risk, adverse selection and impact; do not infer fills from touching a candle price.
7. **Statistical gate:** pre-register primary metric as mean net excess return with dependence-aware block-bootstrap confidence interval; secondary Sortino, max drawdown duration, expectancy, profit factor, exposure/turnover and cost fraction. Use purged chronological walk-forward with embargo matching label horizon, a locked final holdout, and Holm-Bonferroni/DSR only when assumptions and trial log support them. Require positive net expectancy and economically meaningful effect in multiple untouched folds; otherwise REJECT or INCONCLUSIVE.
8. **Promotion gate:** independent reproduction, then prospective shadow/paper validation with actual observed latency and fees. Never auto-promote, change production MonthlyFisher, or authorize live trading from backtest results alone.

### Immediate next action

Continue with the **non-destructive historical-source coverage and storage estimator**, then seek explicit approval before any bulk depth download. Binance historical depth access requires a whitelisted API account and the documented requested time window must be under seven days; request small coverage windows first and do not place credentials in scripts or logs. Keep the current frozen strategy hash unchanged.
