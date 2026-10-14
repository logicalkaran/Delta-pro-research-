# BTC Scalping Book Research v1

Status: research/paper/replay only. No production execution settings changed.

## Source-derived principles

### Algorithmic and High-Frequency Trading
Relevant sections:
- Ch. 1: Electronic Markets and the Limit Order Book
- Ch. 2: Trading Costs and Measuring Liquidity
- Ch. 4: Price Impact / LOB walking / cancellations
- Ch. 7: Incorporating Order Flow
- Ch. 8: Limit and Market Orders
- Ch. 10: Market Making with Adverse Selection; Short-Term Alpha
- Ch. 12: Order Imbalance; Intraday Features

Implementation implications:
1. Limit orders are subject to price-time priority. A new order at an existing price joins the queue behind visible resting quantity.
2. Spread is an immediate execution cost. A narrow spread is necessary but not sufficient for a good trade.
3. Market impact and visible depth matter even for short-horizon systems; expected movement must exceed trading costs and impact.
4. Order flow can be incorporated as a state variable rather than treating price alone as the signal.
5. Short-term alpha creates adverse-selection risk for passive orders: a limit order can be filled precisely because the market is about to move through it.
6. Order imbalance is a potentially informative short-horizon feature. The book's empirical treatment uses normalized quoted-volume imbalance and examines its relationship with market-order arrivals and subsequent price changes.
7. Therefore, a scalper should evaluate both signal quality and execution quality.

### Trading Exchanges: Market Microstructure Practitioners
Relevant themes:
- liquidity as the ability to trade when desired without significant price effect;
- aggressive orders demand liquidity while passive orders supply it;
- the bid/ask spread is the price paid for immediacy;
- adverse selection is a core component of the economics of spreads;
- liquidity suppliers must distinguish informed/aggressive flow from ordinary liquidity demand.

Implementation implications:
1. Do not equate large resting depth with safe liquidity.
2. Treat aggressive flow plus changing book pressure as a possible information signal.
3. Passive entries require an adverse-selection check, not only a favorable entry price.
4. Execution-quality statistics should be reported separately from directional prediction statistics.

### Barry Johnson — Algorithmic Trading & DMA
The uploaded PDF is present, but its text layer was not machine-readable in the current environment. It is therefore not used for source-specific claims in this revision.

## New research features
strategy/scalping_microstructure_v1.py adds:
- visible same-price queue-ahead estimate;
- top-of-book depth-weighted microprice;
- imbalance persistence and directional flips;
- spread and half-spread;
- visible-depth market-impact proxy;
- passive adverse-selection proxy;
- passive-edge screen combining predicted movement, spread, impact and adverse selection.

These are proxies, not calibrated alpha estimates.

## Current validation finding
Existing short-horizon research was run without adding raw data:
- 2-minute STRONG forecast bucket: 2,231 samples, directional accuracy ~47.9%, mean aligned move negative.
- LOW_VOLATILITY regime: 2,931 samples, directional accuracy ~47.9%, mean aligned move negative.
- Existing scalp-edge cohort file contains only 5 rows; it is insufficient for promotion.
- Existing parameter optimizer found no stable configuration under its current research criteria.

Interpretation: the current short-horizon predictor is not evidence of a tradable edge. The new microstructure layer should be validated as an execution/conditioning layer against replay, not assumed profitable.

## Next validation sequence
1. Replay existing WebSocket/order-book data only; do not start another raw collector.
2. Reconstruct limit-entry lifecycle: submit -> queue ahead -> partial/full fill -> cancel/replace.
3. Measure fill probability and time-to-fill by queue fraction, spread and imbalance persistence.
4. Measure post-fill adverse selection at 1s/5s/15s/30s horizons.
5. Compare passive FVG/OB entries against market-entry counterfactuals.
6. Replace proxy expected-move calculations with empirical forward-move distributions.
7. Walk-forward by session/regime and report expectancy after fees, slippage and missed fills.
8. Keep live execution disabled until the replay evidence passes the existing production-readiness gates.

No production trading code is modified by this research layer.