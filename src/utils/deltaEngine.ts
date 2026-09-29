import { TradeEvent, DeltaBar, MarketRegimeType } from '../types/microstructure';

/**
 * Trade Flow and Delta Imbalance Analytics Engine
 */

export function aggregateTradesIntoDeltaBars(
  trades: TradeEvent[],
  barIntervalSeconds: number = 60
): DeltaBar[] {
  if (trades.length === 0) return [];

  // Sort trades chronologically
  const sorted = [...trades].sort((a, b) => a.exchangeTimestamp - b.exchangeTimestamp);
  const bars: DeltaBar[] = [];

  let currentBarStart = Math.floor(sorted[0].exchangeTimestamp / (barIntervalSeconds * 1000)) * (barIntervalSeconds * 1000);
  let barTrades: TradeEvent[] = [];
  let cumulativeDelta = 0;

  for (let i = 0; i < sorted.length; i++) {
    const t = sorted[i];
    const tradeBarStart = Math.floor(t.exchangeTimestamp / (barIntervalSeconds * 1000)) * (barIntervalSeconds * 1000);

    if (tradeBarStart > currentBarStart && barTrades.length > 0) {
      // Finalize current bar
      const bar = createDeltaBar(currentBarStart, barTrades, cumulativeDelta);
      cumulativeDelta = bar.cumulativeVolumeDelta;
      bars.push(bar);

      // Start new bar
      currentBarStart = tradeBarStart;
      barTrades = [t];
    } else {
      barTrades.push(t);
    }
  }

  // Finalize last bar
  if (barTrades.length > 0) {
    const bar = createDeltaBar(currentBarStart, barTrades, cumulativeDelta);
    bars.push(bar);
  }

  // Calculate rolling features across bars
  computeRollingDeltaFeatures(bars);

  return bars;
}

function createDeltaBar(
  timestamp: number,
  trades: TradeEvent[],
  previousCVD: number
): DeltaBar {
  const prices = trades.map((t) => t.price);
  const open = prices[0];
  const close = prices[prices.length - 1];
  const high = Math.max(...prices);
  const low = Math.min(...prices);

  let buyVol = 0;
  let sellVol = 0;
  let buyCount = 0;
  let sellCount = 0;

  for (const t of trades) {
    if (t.side === 'buy') {
      buyVol += t.size;
      buyCount++;
    } else {
      sellVol += t.size;
      sellCount++;
    }
  }

  const totalVol = buyVol + sellVol;
  const signedDelta = buyVol - sellVol;
  const cumulativeVolumeDelta = previousCVD + signedDelta;
  const totalTrades = buyCount + sellCount;
  const tradeCountImbalance = totalTrades > 0 ? (buyCount - sellCount) / totalTrades : 0;

  const dateObj = new Date(timestamp);
  const timeString = `${dateObj.getHours().toString().padStart(2, '0')}:${dateObj
    .getMinutes()
    .toString()
    .padStart(2, '0')}:${dateObj.getSeconds().toString().padStart(2, '0')}`;

  return {
    timestamp,
    timeString,
    open: Number(open.toFixed(2)),
    high: Number(high.toFixed(2)),
    low: Number(low.toFixed(2)),
    close: Number(close.toFixed(2)),
    volume: Number(totalVol.toFixed(4)),
    buyVolume: Number(buyVol.toFixed(4)),
    sellVolume: Number(sellVol.toFixed(4)),
    signedDelta: Number(signedDelta.toFixed(4)),
    cumulativeVolumeDelta: Number(cumulativeVolumeDelta.toFixed(4)),
    tradeCount: totalTrades,
    buyTradeCount: buyCount,
    sellTradeCount: sellCount,
    tradeCountImbalance: Number(tradeCountImbalance.toFixed(4)),
    orderBookImbalance: 0,
    micropriceDelta: 0,
    rollingDeltaAcceleration: 0,
    deltaPriceDivergence: 0,
    priceImpactPerVolume: 0,
    flowPersistence: 0,
    marketRegime: 'normal',
  };
}

/**
 * Compute multi-bar rolling acceleration, divergence, and price impact
 */
export function computeRollingDeltaFeatures(bars: DeltaBar[]): void {
  const window = 5;

  for (let i = 0; i < bars.length; i++) {
    const b = bars[i];
    const prev = i > 0 ? bars[i - 1] : null;

    // Price change in basis points
    const priceChangeBps = prev && prev.close > 0 ? ((b.close - prev.close) / prev.close) * 10000 : 0;

    // Price Impact: bps per unit volume
    if (b.volume > 0 && Math.abs(b.signedDelta) > 0.01) {
      b.priceImpactPerVolume = Number((priceChangeBps / Math.abs(b.signedDelta)).toFixed(4));
    }

    // Rolling Delta Acceleration (Delta of Signed Delta over window)
    if (i >= window) {
      let recentDeltaSum = 0;
      let olderDeltaSum = 0;
      for (let j = 0; j < window; j++) {
        recentDeltaSum += bars[i - j].signedDelta;
        olderDeltaSum += bars[i - window - j]?.signedDelta || 0;
      }
      b.rollingDeltaAcceleration = Number((recentDeltaSum - olderDeltaSum).toFixed(4));
    }

    // Delta-Price Divergence calculation:
    // Positive divergence: Price dropping but buyers aggressively absorbing (+delta) -> Bullish Divergence (+1)
    // Negative divergence: Price rising but aggressive selling (-delta) -> Bearish Divergence (-1)
    if (prev) {
      const priceDirection = b.close - prev.close;
      const deltaDirection = b.signedDelta;

      if (priceDirection > 0 && deltaDirection < 0) {
        // Bearish exhaustion
        b.deltaPriceDivergence = -1;
      } else if (priceDirection < 0 && deltaDirection > 0) {
        // Bullish absorption
        b.deltaPriceDivergence = 1;
      } else {
        b.deltaPriceDivergence = 0;
      }
    }

    // Flow persistence (1-lag direction agreement)
    if (prev) {
      const sameDirection = Math.sign(b.signedDelta) === Math.sign(prev.signedDelta);
      b.flowPersistence = sameDirection ? 1 : -1;
    }

    // Simple market regime categorization
    if (b.volume > 50 && Math.abs(priceChangeBps) > 20) {
      b.marketRegime = 'high_volatility';
    } else if (Math.abs(priceChangeBps) < 3) {
      b.marketRegime = 'ranging_choppy';
    } else if (priceChangeBps > 10) {
      b.marketRegime = 'trending_bull';
    } else if (priceChangeBps < -10) {
      b.marketRegime = 'trending_bear';
    } else {
      b.marketRegime = 'normal';
    }
  }
}
