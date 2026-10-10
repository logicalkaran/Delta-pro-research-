# BTC Fisher / Delta Paper Trading Platform — Consolidation Report

Date: 2026-10-05
Mode: PAPER ONLY
Live exchange orders: DISABLED

## Architecture
Delta WebSocket -> live market state -> 1-minute candle builder -> strategy/research layer -> risk gate -> persistent paper engine -> dashboard.

The dashboard is read-only, exposes no order-submission API, and binds to localhost.

## Components
- Frozen MonthlyFisher: HL2, length 10, alpha 0.33, beta 0.67.
- Decision engine: quality gate + scored evidence.
- Risk engine: max positions, order notional, daily loss limit, kill switch, position sizing.
- Paper engine: persistent LONG/SHORT positions, explicit close/reversal semantics, unrealized P&L.
- Delta collector: trades + L1/L2 subscriptions.
- Live market state: atomic bid/ask/last-trade state.
- Candle engine: rolling 1-minute OHLCV, 240-candle cap.
- Dashboard: live price, bid/ask, flow, Fisher, paper state and candlestick chart.
- Health endpoint: /health.
- State endpoint: /api/state.

## Safety
1. Live order submission is disabled.
2. Dashboard accepts no POST order requests.
3. Paper execution requires the existing risk engine.
4. Same-direction paper positions cannot be silently duplicated.
5. Reversal requires an explicit close first.
6. Persisted trade state is written atomically.
7. Strategy visualization is not automatically promoted to execution.
8. Missing/low-quality evidence remains non-tradable.

## Verified state
Delta WebSocket was updating BTCUSD live during consolidation. Observed mid prices were around 86,116–86,141 USD with a 0.5 USD spread. Monthly Fisher latest completed month was 2026-09, Fisher approximately -1.38689, trigger approximately -2.03888, bullish cross false. Paper position was none.

## Validation
Python compilation: PASS.
Pytest: PASS — 2 passed.
Short open/close and P&L test: PASS.
Live market-state updates: PASS.
1-minute candle generation: PASS.
Dashboard state API: PASS during live verification.
Health checks: PASS.

## Trading status
This is a robust paper-trading/research foundation, not a guarantee of profitability. The intraday overlay remains research-only until RSI/SMC/order-flow evidence is formally wired and validated with out-of-sample and walk-forward tests.

## Next target
Complete the unified intraday evidence engine: RSI + structure/SMC + trend + volume + order-flow, timestamp-aligned with explicit data-quality scoring. Feed it into the existing decision/risk pipeline and record every decision for statistical auditing.
