# Isolated Order Block experiment — BTCUSD 15m

Research sandbox only. It does not import or mutate MonthlyFisher, the Decision Engine, production risk configuration, exchange execution, or production paper engine. It makes only public read-only candle requests and has no order-placement code.

Rules:
- 15-minute Delta BTCUSD OHLCV.
- Swing pivots confirmed only after two right-side candles.
- Candidate block requires a close through the latest confirmed swing and displacement body >= 0.8 ATR.
- Zone is the last opposing candle within five bars: bullish [low, open], bearish [open, high].
- Wait for a later candle to overlap the zone and close in trade direction; enter at next bar open.
- Stop beyond zone plus 0.1 ATR (or 0.01% price) buffer; target 2R; maximum hold 48 bars.
- Unused zones expire after 96 bars (24 hours) to avoid treating stale zones as active.
- One simulated position at a time. If stop and target are both touched within one candle, assume stop first.
- Default costs: 5 bps fee plus 2 bps slippage per side. These are research assumptions, not verified account fees.

Run from repository root:
    .venv/bin/python research/order_block_v1/order_block_experiment.py --days 180

Optional local CSV:
    .venv/bin/python research/order_block_v1/order_block_experiment.py --input path/to/candles.csv

Outputs are isolated in research/order_block_v1/output/; historical candles are saved to research/order_block_v1/btcusd_15m.csv. The local JSONL paper ledger is not connected to production paper trading.

The final 30% of candles is a chronological holdout. Do not tune rules on that holdout and then describe it as untouched. Require cost sensitivity, parameter sensitivity, data-gap checks, enough holdout trades, and additional forward paper observation before any promotion. A positive backtest is not a profit guarantee or live-trading approval.
