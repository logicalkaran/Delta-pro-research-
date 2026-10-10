# Institutional Testing Specification — Implementation Status

Date: 2026-10-10
Scope: existing `btc_fisher_trader`; paper/shadow and mock-only additions.
Production strategy and live execution gates remain unchanged.

## Deterministic risk tests

Implemented and tested:
- Risk oracle rejects new entries when daily, weekly or peak drawdown fuses trip; risk-reducing decisions are separately classified.
- Adverse 5% shock and maintenance-margin headroom are checked by the pure oracle.
- `risk/concurrent_risk_gate.py` serializes concurrent intents and reserves approved quantities before a second decision. Eight concurrent test threads cannot reserve beyond the configured 0.001 BTC aggregate cap.
- A reservation cannot be released until cancellation is confirmed or a fill is reconciled into the authoritative snapshot.

Not implemented:
- No adapter currently injects the live MonthlyFisher decision and authenticated account snapshot into the concurrent gate. It remains a pure policy wrapper and test fixture.

## TWAP persistence and queue chase

Implemented and tested in `execution/twap_ledger.py`:
- A 1 BTC parent is represented as ten 0.1 BTC children scheduled 12 minutes apart across a two-hour interval.
- Parent creation is idempotent for the same ID and exact parameters; parameter mismatch is rejected.
- Child state is persisted before any dispatch can be attempted. Stable client IDs make reconciliation possible.
- After restart, open-order matches are retained; any child absent from open orders while in flight becomes UNKNOWN and requires private order/fill-history reconciliation. Unknown orders are never blindly resent.
- Only one child can be in flight per parent; this prevents an Android resume from bursting multiple overdue children at once. Missed TWAP intervals are not automatically caught up.
- A child can be marked FILLED/CANCELED/REJECTED only after an authoritative result is supplied, with the filled quantity persisted. Parent state and remaining quantity are derived from child results.
- Passive repricing rejects off-tick inputs, enforces a three-tick chase ceiling, never crosses the spread, and otherwise waits for the next interval.

Boundary: this is a SQLite ledger and deterministic policy, not a live TWAP runner. There is no wall-clock scheduler or exchange submit/cancel integration. The exchange must support stable client order IDs and the caller must reconcile both open orders and private order history. Partial-fill residual reallocation to later children is not yet implemented.

## Circuit breaker and emergency sequence

Implemented and tested:
- WebSocket latency above 500 ms, missed heartbeat, stale feed, supervisor loss, and memory telemetry above the configured 500 MB threshold trip the pure watchdog.
- `execution/emergency_sequence.py` calls an injected adapter in order: halt signal ingestion, set emergency state, request global cancellation of open limit orders, then append an audit event.
- Cancellation is reported confirmed only if the adapter response explicitly contains `success=True` and `confirmed=True`. Exceptions/unconfirmed responses are errors, not success.
- Results separately expose whether signal ingestion was halted and whether emergency state was persisted.

Boundary: the tests use mocks. No real REST cancel-all request was sent. There is no independent watchdog process or Android Low Memory Killer experiment; telemetry threshold fuzzing does not prove actual memory pre-emption or prevent Android from killing Termux.

## Verification

Run the full repository suite:

```sh
cd ~/btc_fisher_trader
.venv/bin/python -m pytest -q
git diff --check
./maintenance/edge_node_healthcheck.sh
```

A passing suite verifies deterministic software behavior for tested scenarios. It does not prove profitable edge, actual exchange cancel behavior, crash timing at every instruction, exchange idempotency, or 24/7 Android uptime.

## Live status

`execution/LIVE_PROMOTION_POLICY.json` remains `BLOCKED_UNTIL_VALIDATED`.
`execution/LIVE_TRADING_STATUS.txt` continues to state `REAL ORDER SUBMISSION: DISABLED`.
No strategy code was intentionally changed by this testing milestone, and no live exchange calls or orders were made.
