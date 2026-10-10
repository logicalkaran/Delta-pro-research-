# BTC Fisher Trading Engine — Engineering Status

## Purpose

Research and paper-trading system for BTC perpetual market data, signal evaluation, execution simulation, risk controls, and crash recovery. This repository is not approved for production capital. A production-style code layout does not mean the strategy is profitable or exchange execution has been validated.

## Safety status

- Real order submission: DISABLED by default.
- Promotion policy: BLOCKED_UNTIL_VALIDATED.
- Existing MonthlyFisher baseline is preserved; research variants must remain separate.
- The account-state adapter is GET-only and has no order mutation methods.
- Delta API-key permissions must be restricted in the exchange dashboard; HMAC authentication does not prove a key is read-only.

## Current architecture

1. Market-data collection and microstructure feature processing.
2. Frozen signal/decision components and isolated research alternatives.
3. Risk oracle for signed BTC exposure, 5% adverse shock, maintenance-margin headroom, and daily/weekly/peak drawdown fuses.
4. SQLite WAL event journal with canonical payloads and SHA-256 hash chaining.
5. Paper execution, TWAP ledger, reconciliation, and crash-recovery components.
6. Fail-closed live promotion and operator gates.

## Authoritative account risk gate

`execution/authoritative_account_risk.py` rejects stale or incomplete account snapshots, missing historical equity anchors, malformed values, unknown contract-to-BTC conversion, and stress-margin breaches. It combines the authoritative signed position with proposed signed BTC quantity before evaluating risk. Scaled quantities are not routed through a fixed-contract order API until lot/contract conversion is independently verified.

The controller preflight now checks account-state age against a 5-second limit before evaluating the signal. It sources account values through `exchange/delta_state_adapter.py` and drawdown anchors from `storage/event_journal.py`. The journal must contain `DAILY_EQUITY_ANCHOR`, `WEEKLY_EQUITY_ANCHOR`, and `PEAK_EQUITY_ANCHOR` events before risk approval is possible.

Important limitation: the adapter currently timestamps account-state observation locally after the API response; this is not proof of an exchange-origin timestamp. Delta position parsing deliberately requires explicitly BTC-denominated fields rather than assuming inverse-contract `size` equals BTC. If the adapter cannot verify denomination, it rejects.

## Verification

Run `python -m compileall -q .`, `python -m pytest -q`, `git diff --check`, and `python -m execution.production_audit`.

## Promotion blockers

- Current recorded paper sample is insufficient and negative: 6 trades, average net return about -9.24 bps, profit factor about 0.027.
- Complete chronological walk-forward and multiple-regime paper evaluation.
- Verify fee, funding, contract specifications, account state, and execution costs against Delta.
- Validate independent watchdog, private fill-history reconciliation, external hash anchors, and a real 72-hour shadow burn-in.
- Add static analysis, coverage thresholds, release tagging, and reviewed CI.
- Verify controller behavior with read-only credentials and real exchange responses without sending orders.

## Operating rule

Do not promote the policy, set live arming environment variables, or submit/cancel real orders as part of development validation. A green unit suite is not evidence of profitability or live readiness.