# Order Block Research v1 — BTCUSD 15m

**Mode:** isolated research-only local paper simulation. **Live execution:** disabled.

- Source: research/order_block_v1/btcusd_15m.csv
- Candles: 17280
- UTC range: 2026-04-13T23:15:00+00:00 to 2026-10-10T23:00:00+00:00
- Cost assumption: 5.00 bps fee + 2.00 bps slippage per side
- Entry: next candle open after retest/confirmation; target 2R; max hold 48 bars.
- Same-bar stop/target collision resolves stop-first; one position at a time.
- Split: isolated chronological first 70% exploratory, final 30% holdout; zones and positions reset.

## Training period

- Trades: 307
- Net win rate: 0.3062
- Gross expectancy (R/trade): -0.0724
- Net expectancy (R/trade): -0.8662
- Gross profit factor: 0.8931
- Net profit factor: 0.3113
- Average cost (R/trade): 0.7938
- Average risk width (bps): 31.2883
- Net total (R): -265.9131
- Max drawdown (R): 267.2262
- Long / short: 149 / 158

## Out-of-sample holdout

- Trades: 131
- Net win rate: 0.3817
- Gross expectancy (R/trade): 0.1779
- Net expectancy (R/trade): -0.5789
- Gross profit factor: 1.3003
- Net profit factor: 0.4451
- Average cost (R/trade): 0.7568
- Average risk width (bps): 29.2586
- Net total (R): -75.8368
- Max drawdown (R): 78.0128
- Long / short: 69 / 62

## All sample (descriptive only)

- Trades: 438
- Net win rate: 0.3288
- Gross expectancy (R/trade): 0.0025
- Net expectancy (R/trade): -0.7803
- Gross profit factor: 1.0038
- Net profit factor: 0.3463
- Average cost (R/trade): 0.7827
- Average risk width (bps): 30.6812
- Net total (R): -341.7499
- Max drawdown (R): 345.2389
- Long / short: 218 / 220

## Cost sensitivity (all sample)

| Fee bps/side | Slippage bps/side | Net expectancy (R/trade) | Net profit factor |
|---:|---:|---:|---:|
| 2.0 | 1.0 | -0.3330 | 0.6215 |
| 5.0 | 2.0 | -0.7803 | 0.3463 |
| 8.0 | 4.0 | -1.3393 | 0.1752 |

## Validation warnings

- Holdout net expectancy is non-positive; do not promote this rule set.
- Modeled transaction costs exceed holdout gross expectancy; the current edge does not cover costs.

This is not live-readiness approval or a claim of future profitability.
