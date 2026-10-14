# Orchestration Tier milestone — BTC Fisher / Delta Exchange

## Implemented in this milestone

- Added `risk/orchestration_oracle.py`: pure local risk decision function with APPROVED, SCALED, REJECTED and REDUCE_ONLY outcomes.
- Added an adverse 5% price-shock check against net current + proposed BTC exposure.
- Added an explicit minimum stressed maintenance-margin headroom threshold.
- Added daily, weekly and peak-to-trough drawdown fuses.
- Added fail-closed checks for stale market data, WebSocket latency, memory ceiling, kill switch, non-finite inputs and invalid risk configuration.
- Added focused unit tests in `risk/test_orchestration_oracle.py`.

## Deliberately not connected to real order submission

The existing `data/live_microstructure_state.json` contains market/microstructure data but does not contain authoritative account equity, daily/weekly/peak equity anchors, current account position and exchange maintenance-margin parameters together. Therefore the new oracle must not be fed invented zeros or estimates and must not be used to authorize live orders yet.

The current live promotion policy remains BLOCKED_UNTIL_VALIDATED and order submission remains disabled. This milestone does not change MonthlyFisher, existing production strategies, credentials, or live-order flags.

## Required next integration gates

1. Implement a read-only account snapshot adapter from authoritative Delta account/position endpoints; validate units, timestamps, completeness and account/product identity.
2. Persist daily-start, weekly-start and peak-equity anchors atomically with recovery and audit checks.
3. Reconcile open orders, partial fills and positions before any order intent is evaluated.
4. Add a separately supervised watchdog and explicit REST recovery/cancel workflow. Never claim that an emergency cancel succeeded without exchange confirmation.
5. Connect the oracle to paper/shadow execution first; test restart recovery, stale feeds, latency spikes, memory pressure, API failures and partial fills.
6. Require deterministic replay and realistic cost-aware walk-forward evidence before considering any promotion. Live execution stays disabled until explicit review and approval.

## Threshold interpretation

The initial limits in the new module are conservative engineering defaults for testing, not validated trading parameters or a promise of safety. In particular, the 0.001 BTC exposure cap, 2% daily drawdown, 5% weekly drawdown, 10% peak drawdown and 500 ms / 500 MB watchdog thresholds require explicit account-specific validation before deployment.

- Added `risk/orchestration_watchdog.py`: pure watchdog policy evaluator for heartbeat loss, latency, stale market data, memory pressure and supervisor health. It emits emergency actions required, but does not pretend to execute or confirm REST cancellations.
- Added `risk/test_orchestration_watchdog.py` for normal, breached, non-finite and invalid-configuration scenarios.

## Watchdog execution boundary

The watchdog evaluator is currently a tested policy core, not a separately running OS process. A production supervisor still needs to run independently of the collector/trading loop, issue REST cancellations, reconcile open orders/positions, persist emergency state and verify exchange acknowledgements. The dashboard must not be treated as the watchdog.
