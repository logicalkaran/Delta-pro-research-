import { Candle, AlgoStrategy, BacktestResult, BacktestTrade } from '../types/crypto';
import { calculateEMA, calculateRSI, calculateBollingerBands } from './indicators';

export function runBacktest(
  candles: Candle[],
  strategy: AlgoStrategy,
  symbol: string = 'BTCUSD',
  initialCapitalUsd: number = 10000
): BacktestResult {
  if (candles.length < 30) {
    return {
      strategyName: strategy.name,
      symbol,
      totalReturnPercent: 0,
      winRatePercent: 0,
      profitFactor: 0,
      maxDrawdownPercent: 0,
      totalTrades: 0,
      winningTrades: 0,
      losingTrades: 0,
      trades: [],
    };
  }

  const closes = candles.map((c) => c.close);
  const fastEMA = calculateEMA(closes, strategy.fastPeriod || 20);
  const slowEMA = calculateEMA(closes, strategy.slowPeriod || 50);
  const rsi = calculateRSI(closes, 14);
  const bb = calculateBollingerBands(closes, 20, strategy.bbStdDev || 2);

  const trades: BacktestTrade[] = [];
  let capital = initialCapitalUsd;
  let peakCapital = initialCapitalUsd;
  let maxDrawdown = 0;

  let inPosition: {
    type: 'BUY' | 'SELL';
    entryTime: number;
    entryPrice: number;
    candleIndex: number;
  } | null = null;

  const leverage = Math.min(strategy.leverage || 5, 25);
  const stopLossPct = (strategy.stopLossPercent || 2.5) / 100;
  const takeProfitPct = (strategy.takeProfitPercent || 5.0) / 100;

  for (let i = 30; i < candles.length; i++) {
    const c = candles[i];
    const prevC = candles[i - 1];
    const currentPrice = c.close;

    // Check open position exit first
    if (inPosition) {
      let shouldExit = false;
      let exitPrice = currentPrice;
      let reason = '';

      if (inPosition.type === 'BUY') {
        const gain = (currentPrice - inPosition.entryPrice) / inPosition.entryPrice;
        if (gain >= takeProfitPct) {
          shouldExit = true;
          exitPrice = inPosition.entryPrice * (1 + takeProfitPct);
          reason = `Take Profit (+${(takeProfitPct * 100).toFixed(1)}%)`;
        } else if (gain <= -stopLossPct) {
          shouldExit = true;
          exitPrice = inPosition.entryPrice * (1 - stopLossPct);
          reason = `Stop Loss (-${(stopLossPct * 100).toFixed(1)}%)`;
        } else if (strategy.type === 'momentum' && fastEMA[i] && slowEMA[i] && fastEMA[i]! < slowEMA[i]!) {
          shouldExit = true;
          reason = 'EMA Bearish Cross Exit';
        } else if (strategy.type === 'mean_reversion' && bb.upper[i] && currentPrice >= bb.upper[i]!) {
          shouldExit = true;
          reason = 'Upper Bollinger Band Target';
        }
      } else if (inPosition.type === 'SELL') {
        const gain = (inPosition.entryPrice - currentPrice) / inPosition.entryPrice;
        if (gain >= takeProfitPct) {
          shouldExit = true;
          exitPrice = inPosition.entryPrice * (1 - takeProfitPct);
          reason = `Take Profit (+${(takeProfitPct * 100).toFixed(1)}%)`;
        } else if (gain <= -stopLossPct) {
          shouldExit = true;
          exitPrice = inPosition.entryPrice * (1 + stopLossPct);
          reason = `Stop Loss (-${(stopLossPct * 100).toFixed(1)}%)`;
        } else if (strategy.type === 'momentum' && fastEMA[i] && slowEMA[i] && fastEMA[i]! > slowEMA[i]!) {
          shouldExit = true;
          reason = 'EMA Bullish Cross Exit';
        }
      }

      if (shouldExit || i === candles.length - 1) {
        if (!reason) reason = 'End of backtest period';
        const rawReturn = inPosition.type === 'BUY'
          ? (exitPrice - inPosition.entryPrice) / inPosition.entryPrice
          : (inPosition.entryPrice - exitPrice) / inPosition.entryPrice;

        const leveragedReturn = rawReturn * leverage;
        const tradePnlUsd = capital * 0.2 * leveragedReturn; // 20% portfolio size per trade
        capital += tradePnlUsd;

        if (capital > peakCapital) peakCapital = capital;
        const dd = ((peakCapital - capital) / peakCapital) * 100;
        if (dd > maxDrawdown) maxDrawdown = dd;

        trades.push({
          id: `trade-${trades.length + 1}`,
          type: inPosition.type,
          entryTime: inPosition.entryTime,
          exitTime: c.time,
          entryPrice: Number(inPosition.entryPrice.toFixed(2)),
          exitPrice: Number(exitPrice.toFixed(2)),
          pnlPercent: Number((leveragedReturn * 100).toFixed(2)),
          pnlUsd: Number(tradePnlUsd.toFixed(2)),
          reason,
        });

        inPosition = null;
      }
    }

    // Check entry signal if not in position
    if (!inPosition && i < candles.length - 1) {
      if (strategy.type === 'momentum') {
        // Fast EMA crosses above Slow EMA
        const prevFast = fastEMA[i - 1];
        const prevSlow = slowEMA[i - 1];
        const currFast = fastEMA[i];
        const currSlow = slowEMA[i];

        if (prevFast && prevSlow && currFast && currSlow) {
          if (prevFast <= prevSlow && currFast > currSlow && (rsi[i] || 50) > 48) {
            inPosition = {
              type: 'BUY',
              entryTime: c.time,
              entryPrice: currentPrice,
              candleIndex: i,
            };
          } else if (prevFast >= prevSlow && currFast < currSlow && (rsi[i] || 50) < 52) {
            inPosition = {
              type: 'SELL',
              entryTime: c.time,
              entryPrice: currentPrice,
              candleIndex: i,
            };
          }
        }
      } else if (strategy.type === 'mean_reversion') {
        // Price pierces lower BB and RSI < 35
        if (bb.lower[i] && currentPrice < bb.lower[i]! && (rsi[i] || 50) < 36) {
          inPosition = {
            type: 'BUY',
            entryTime: c.time,
            entryPrice: currentPrice,
            candleIndex: i,
          };
        } else if (bb.upper[i] && currentPrice > bb.upper[i]! && (rsi[i] || 50) > 65) {
          inPosition = {
            type: 'SELL',
            entryTime: c.time,
            entryPrice: currentPrice,
            candleIndex: i,
          };
        }
      } else if (strategy.type === 'funding_arbitrage') {
        // Steady yield harvesting entries every 15-20 candles
        if (i % 16 === 0) {
          inPosition = {
            type: 'BUY',
            entryTime: c.time,
            entryPrice: currentPrice,
            candleIndex: i,
          };
        }
      } else if (strategy.type === 'breakout') {
        // Highest high breakout of last 15 candles with volume
        let highest = 0;
        let avgVol = 0;
        for (let j = i - 15; j < i; j++) {
          if (candles[j].high > highest) highest = candles[j].high;
          avgVol += candles[j].volume;
        }
        avgVol /= 15;

        if (currentPrice > highest && c.volume > avgVol * 1.3) {
          inPosition = {
            type: 'BUY',
            entryTime: c.time,
            entryPrice: currentPrice,
            candleIndex: i,
          };
        }
      } else {
        // Default hybrid / AI custom
        if ((rsi[i] || 50) < 42 && fastEMA[i] && currentPrice > fastEMA[i]! * 0.995) {
          inPosition = {
            type: 'BUY',
            entryTime: c.time,
            entryPrice: currentPrice,
            candleIndex: i,
          };
        }
      }
    }
  }

  const winningTrades = trades.filter((t) => t.pnlPercent > 0);
  const losingTrades = trades.filter((t) => t.pnlPercent <= 0);

  const totalGain = winningTrades.reduce((acc, t) => acc + t.pnlUsd, 0);
  const totalLoss = Math.abs(losingTrades.reduce((acc, t) => acc + t.pnlUsd, 0));
  const profitFactor = totalLoss === 0 ? (totalGain > 0 ? 9.99 : 1.0) : totalGain / totalLoss;

  const winRatePercent = trades.length > 0 ? (winningTrades.length / trades.length) * 100 : 0;
  const totalReturnPercent = ((capital - initialCapitalUsd) / initialCapitalUsd) * 100;

  return {
    strategyName: strategy.name,
    symbol,
    totalReturnPercent: Number(totalReturnPercent.toFixed(2)),
    winRatePercent: Number(winRatePercent.toFixed(1)),
    profitFactor: Number(profitFactor.toFixed(2)),
    maxDrawdownPercent: Number(maxDrawdown.toFixed(2)),
    totalTrades: trades.length,
    winningTrades: winningTrades.length,
    losingTrades: losingTrades.length,
    trades: trades.reverse(), // most recent first
  };
}
