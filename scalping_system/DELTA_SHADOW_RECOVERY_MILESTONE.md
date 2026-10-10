# Delta Read-Only State + Paper Shadow + Crash Recovery Milestone

Date: 2026-10-10

## Scope and safety boundary

This milestone adds three isolated components:
- `exchange/delta_state_adapter.py`: authenticated GET-only access to allowlisted Delta v2 state endpoints.
- `execution/paper_simulator.py`: local matching and fee/equity simulation driven by caller-supplied market snapshots and explicit trade prints.
- `recovery/state_reconciler.py`: hash-chain verification and deterministic parent/child reconstruction.

It does not connect to live order controllers or submit/cancel/modify exchange orders. If local dispatch state is ambiguous, reconciliation returns `UNKNOWN`; if the exchange reports a locally unacknowledged child as open, it reports `CANCEL_REQUIRED` and blocks resume. It does not automatically cancel a real order because cancellation is a mutating operation and live execution remains disabled.

## Read-only Delta adapter

The adapter reads credentials from environment variables only and signs GET requests using the existing Delta signer. Allowlisted paths are `/v2/wallets`, `/v2/positions/margined`, and `/v2/orders`. It has no public generic request, place-order, or cancel-order method.

Configure a read-only API key in Delta API Management. HMAC signatures authenticate requests but do not prove that the key lacks trading permissions; successful reads must not be treated as permission verification. Account fields are extracted only when present. Missing equity/margin data is represented as `None`; open interest is not inferred from account position payloads.

The adapter can append one `AUTHORITATIVE_EQUITY_ANCHOR` event per UTC hour to `storage/event_journal.py`; duplicate polls in the same hour are idempotent and missing equity is not anchored. The hash chain detects retained-chain edits, but truncation protection still requires an independently retained terminal hash/sequence.

The current Termux environment has `requests` available and `aiohttp` absent, so the adapter uses the existing `requests` transport with injection for unit tests. No packages were installed. Tests use mocked transport and do not issue HTTP requests.

## Paper simulator assumptions

Market data must be supplied by a separate caller; no always-on websocket process was added. Feed snapshots must include timestamp, bid/ask, mark and displayed top-of-book sizes. Stale, crossed or invalid snapshots fail closed.

Marketable orders can fill only against the supplied top-of-book size. A remaining quantity is not filled against imaginary deeper levels. Passive orders remain resting until an explicit trade print crosses their limit in the appropriate direction; a top-of-book snapshot alone does not establish queue position.

Defaults are 100–400 ms simulated acknowledgement latency, a 0.05% taker fee, and a 0.02% maker rebate. These are configurable research assumptions, not a verified current Delta fee schedule. Validate fee tier and rebate eligibility before using results for cost conclusions. The simulator does not alter MonthlyFisher or make strategy decisions; adaptive pacing is exposed only as a recommendation.

## Crash recovery and SIGKILL proof

The tests spawn a separate Python process, durably append parent/child events to a temporary SQLite WAL journal, then kill that process after dispatch persistence and before acknowledgement. A second case includes a partial fill and a subsequent unacknowledged child. The test reopens the journal, verifies its hash chain, replays events, and asserts:
- exactly one dispatch record per submitted child;
- no fabricated acknowledgement/fill after the kill;
- unknown child state blocks resumption;
- parent remaining size equals parent quantity minus recorded fill quantity.

This validates local SQLite/journal replay under the tested crash points. It does not prove Delta's live API behavior, external key permissions, Android scheduling reliability, or correctness under every possible crash boundary.

## Verification

```sh
cd ~/btc_fisher_trader
.venv/bin/python -m pytest -q exchange/test_delta_state_adapter.py execution/test_paper_simulator.py recovery/test_state_reconciler.py
.venv/bin/python -m pytest -q
git diff --check
./maintenance/edge_node_healthcheck.sh
```

Live promotion policy must remain `BLOCKED_UNTIL_VALIDATED` and `REAL ORDER SUBMISSION: DISABLED`. Future production readiness still requires reviewed authenticated account-state mapping, private order/fill-history reconciliation, independently confirmed key permissions, current fee-tier verification, external journal anchoring, and a separately approved cancellation/execution integration.
