# BTC Edge Node — Architecture and Quantitative Specification

Status: engineering specification / paper-shadow only. No authorization for live orders.

## 1. System boundary

Market feeds (Delta BTC perpetual, optional Binance reference feeds)
→ schema validation / exchange-time and local-arrival timestamps
→ bounded market-data buffers
→ microstructure features (trade delta, OFI, imbalance, microprice, spread, volatility)
→ strategy hypothesis / existing MonthlyFisher and decision engine (unchanged)
→ risk oracle (portfolio delta, stress headroom, drawdown fuses)
→ paper/shadow execution and conservative fill-cost model
→ event journal / reconciliation
→ dashboard and quality watchdog.

Cross-venue execution is a separate subsystem. A directional signal is not itself an instruction to hedge or trade. Every execution intent must be checked against authoritative account, position, open-order and product metadata from each venue.

## 2. Edge hypothesis and limits

The testable hypothesis is that a matched spot/perpetual portfolio can reduce first-order BTC price exposure while collecting a positive net funding/basis return. It is not market-neutral in every state and is not guaranteed profitable.

For spot quantity Qs and linear perpetual quantity Qp, expressed in BTC-equivalent delta:

    delta_net = Qs + delta_perp * Qp
    delta_perp = -1 for a short linear BTC perpetual

    delta_net ≈ Qs - |Qp|

The hedge ratio is |Qp| / Qs. The target is close to 1 only after contract multiplier, quote currency, inverse/linear payoff and venue position conventions are normalized. Use the actual instrument delta where it differs from 1.

For a single funding interval:

    funding_pnl = - signed_perp_notional * funding_rate
    net_carry = funding_pnl - fees - spread_cost - slippage - borrow_cost

The sign convention above assumes signed perpetual notional is positive for a long and positive funding means longs pay shorts. Funding must be read from each venue's contract specification and confirmed by tests; never infer signs from a display label.

Total economic PnL must include spot PnL, perpetual PnL, basis changes, funding, borrow, trading fees, slippage, partial-fill exposure and transfer/custody costs. The carry estimate in `risk/hedge_coordinator.py` is intentionally only a funding-interval estimate and explicitly excludes basis/borrow risk.

## 3. Edge acceptance equation

A candidate is eligible for shadow evaluation only when:

    expected_gross_edge_bps
      > entry_fee_bps + exit_fee_bps
      + expected_spread_cost_bps + expected_slippage_bps
      + adverse_selection_buffer_bps + funding/borrow allocation_bps

Estimate each cost from realized venue/account data where possible. If a component is unknown, classify the result as unproven; do not silently set it to zero.

Report net expectancy, confidence intervals, profit factor, turnover, drawdown, fill ratio, hedge latency and time spent outside delta tolerance. A positive point estimate alone is insufficient. Evaluate by volatility, liquidity, funding regime and time-of-day cohorts using purged walk-forward splits.

## 4. OFI-aware adaptive execution

For each valid book update, calculate an OFI feature from changes in best bid/ask prices and sizes. A simple displayed-depth imbalance is not equivalent to event-based OFI; preserve this distinction in datasets.

Normalize the feature to [-1, 1]. For a buy, positive OFI is aligned; for a sell, negative OFI is aligned. The adaptive pacing policy currently provides:
- ACCELERATE: aligned OFI and favorable microprice;
- NORMAL: no clear execution advantage;
- SLOW: flow opposes the intended side or microprice is adverse;
- WITHDRAW_PASSIVE: live passive order with adverse microprice threshold crossed;
- HALT_STALE: market telemetry exceeds freshness limits.

These are pacing recommendations only. They do not set prices, place orders, or prove that faster execution improves outcomes. Test the thresholds with out-of-sample queue/fill and adverse-selection studies before wiring to an executor.

## 5. Orphan-leg and hedge breaker

Every leg must have an intent ID, venue order ID/client order ID, requested size, cumulative filled size, average fill price, venue timestamp, local receive timestamp, cancel state and last reconciliation result.

    net_delta = primary_filled_btc - hedge_filled_btc
    hedge_ratio = hedge_filled_btc / primary_filled_btc, if primary > 0
    emergency = abs(net_delta) > max_unhedged_btc
                OR unresolved_leg_age > max_leg_age
                OR fill_mismatch > max_fill_mismatch

On emergency: halt new entries; query both venues by REST; cancel outstanding orders; reconcile actual positions and fills; reduce only the orphaned exposure using exchange-supported reduce-only semantics; verify every response; persist an emergency event; require manual reset. A timeout or network error is not proof of cancellation. The current hedge module computes the policy decision only; the execution workflow is not yet connected.

## 6. Risk oracle

The current pure oracle enforces:
- finite, fresh market and resource telemetry;
- maximum net BTC exposure;
- adverse 5% price-shock scenario;
- stressed equity versus estimated maintenance margin;
- daily, weekly and peak-to-trough drawdown fuses;
- fail-closed rejection of malformed or stale inputs;
- explicit REDUCE_ONLY classification for orders that reduce existing absolute exposure.

The configured values are engineering test defaults, not validated capital limits. Account equity, position, mark/index price, product multiplier and maintenance-margin tiers must come from authoritative endpoints. Do not estimate liquidation risk using only a constant margin rate when the exchange has tiered maintenance requirements.

## 7. Event journal and recovery

`storage/event_journal.py` uses SQLite WAL, synchronous durability settings, canonical JSON and a SHA-256 hash chain. Replay refuses to proceed if the retained chain fails verification.

A hash chain alone cannot detect deletion of its final rows: tail truncation is detected only when the expected terminal hash/sequence is stored independently and passed into verification. A production anchor should be persisted atomically in a separately protected file/service and periodically exported off-device. SQLite WAL is a durability mechanism, not a claim of zero latency or immunity to Android process termination.

On restart: load last trusted anchor; verify journal; rebuild state by deterministic replay; query both exchange accounts and open orders; reconcile all unresolved intents; remain locked on any mismatch. Never blindly resubmit an order merely because its local acknowledgement is missing.

## 8. Android resource and network supervision

Use bounded queues and preallocated buffers only after profiling demonstrates that Python allocation is a bottleneck. Keep raw capture optional, partitioned and retention-limited. Avoid collecting unrelated personal/device data.

Poll process RSS, Android memory pressure, CPU load, thermal zones where readable, WebSocket heartbeat age and request latency. Android may deny thermal/zone file access; unavailable telemetry must be represented as UNKNOWN, not a fabricated safe value. On critical resource pressure, stop new entries, persist state and reconcile; the supervisor must run independently enough to detect collector failure. JobScheduler is best-effort and is not a hard real-time guarantee.

Do not assume uvloop is supported on Android/Termux or that Cython/zero-copy automatically improves end-to-end latency. Benchmark on the actual device. The Gemini CLI currently fails its Android/Termux runtime guard on this node; Codex CLI is available for read-only review.

## 9. Continuous engineering loop

The hourly quality job runs targeted tests. On failure it invokes Codex in read-only mode to produce a diagnosis and proposed diff; it does not auto-edit production trading code. Review the patch, run focused tests and the broader suite, then inspect `git diff` before merging. Preserve all pre-existing uncommitted repository changes.

The Termux JobScheduler command did not return within the diagnostic timeout during setup, so recurring execution must be confirmed with `termux-job-scheduler --pending` before claiming it is active. A passing quality job means code tests passed; it does not prove the process is running 24/7 or that a strategy has positive expectancy.

## 10. Promotion gates

Remain paper/shadow only until all of the following are evidenced:
1. Multi-session feed integrity, exchange/local clock diagnostics and reconnect tests.
2. Realistic fees, funding, queue position, partial fills, cancellation races and latency distributions.
3. Deterministic replay and recovery from killed/restarted processes.
4. Matched-venue delta and basis PnL reconciliation.
5. Purged walk-forward and adverse-regime evaluation with sufficient completed trades.
6. Verified kill switch, reduce-only, cancellation and manual reset tests in demo.
7. Independent review of risk limits, secrets handling, audit anchors and resource behavior.
8. Explicit human approval of any live promotion.

No component promises near-zero risk, constant profits or immunity to underlying price moves.
