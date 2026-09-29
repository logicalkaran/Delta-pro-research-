import { reconstructOrderBook } from './orderBookEngine';
import { aggregateTradesIntoDeltaBars } from './deltaEngine';
import { validateMarketDataBatch } from './dataQualityValidator';
import { calculateMean, calculatePearsonCorrelation, computeDistributionMetrics } from './mathStats';
import { calculateMonthlyFisher } from './monthlyFisherEngine';
import { runResearchExperiment } from './researchLabEngine';
import { TradeEvent } from '../types/microstructure';

export interface TestResultItem {
  name: string;
  category: string;
  passed: boolean;
  message: string;
  durationMs: number;
}

export function runMicrostructureTestSuite(): TestResultItem[] {
  const results: TestResultItem[] = [];

  const runTest = (name: string, category: string, fn: () => void) => {
    const t0 = performance.now();
    try {
      fn();
      results.push({
        name,
        category,
        passed: true,
        message: 'Assertion passed',
        durationMs: Number((performance.now() - t0).toFixed(2)),
      });
    } catch (e: any) {
      results.push({
        name,
        category,
        passed: false,
        message: e?.message || 'Assertion failed',
        durationMs: Number((performance.now() - t0).toFixed(2)),
      });
    }
  };

  // Test 1: Delta & CVD calculation
  runTest('Signed Delta and CVD Math', 'Delta Analytics', () => {
    const dummyTrades: TradeEvent[] = [
      {
        tradeId: 't1',
        symbol: 'BTCUSDT',
        price: 90000,
        size: 1.5,
        side: 'buy',
        exchangeTimestamp: 1000,
        localReceiveTimestamp: 1005,
        isAggressiveBuy: true,
        isAggressiveSell: false,
        value: 135000,
      },
      {
        tradeId: 't2',
        symbol: 'BTCUSDT',
        price: 90010,
        size: 0.5,
        side: 'sell',
        exchangeTimestamp: 2000,
        localReceiveTimestamp: 2005,
        isAggressiveBuy: false,
        isAggressiveSell: true,
        value: 45005,
      },
    ];

    const bars = aggregateTradesIntoDeltaBars(dummyTrades, 60);
    if (bars.length !== 1) throw new Error(`Expected 1 bar, got ${bars.length}`);
    const b = bars[0];
    if (Math.abs(b.buyVolume - 1.5) > 0.001) throw new Error(`Buy volume expected 1.5, got ${b.buyVolume}`);
    if (Math.abs(b.sellVolume - 0.5) > 0.001) throw new Error(`Sell volume expected 0.5, got ${b.sellVolume}`);
    if (Math.abs(b.signedDelta - 1.0) > 0.001) throw new Error(`Signed delta expected 1.0, got ${b.signedDelta}`);
    if (Math.abs(b.cumulativeVolumeDelta - 1.0) > 0.001) throw new Error(`CVD expected 1.0, got ${b.cumulativeVolumeDelta}`);
  });

  // Test 2: Order-Book Imbalance and Microprice
  runTest('Order Book Reconstruction & Microprice', 'Order Book', () => {
    // Best bid 90000 (size 2.0), Best ask 90002 (size 1.0)
    // Microprice = (1.0 * 90000 + 2.0 * 90002) / 3.0 = (90000 + 180004) / 3 = 270004 / 3 = 90001.33
    const rawBids: [number, number][] = [
      [90000, 2.0],
      [89999, 5.0],
    ];
    const rawAsks: [number, number][] = [
      [90002, 1.0],
      [90003, 3.0],
    ];

    const book = reconstructOrderBook('BTCUSDT', 1000, 1, rawBids, rawAsks);
    if (book.bestBid !== 90000) throw new Error(`Expected bestBid 90000, got ${book.bestBid}`);
    if (book.bestAsk !== 90002) throw new Error(`Expected bestAsk 90002, got ${book.bestAsk}`);
    if (book.spread !== 2) throw new Error(`Expected spread 2, got ${book.spread}`);
    if (Math.abs(book.microprice - 90001.33) > 0.05) throw new Error(`Expected microprice 90001.33, got ${book.microprice}`);
    if (book.isCrossed) throw new Error('Expected uncrossed book');
  });

  // Test 3: Crossed Book Detection
  runTest('Crossed Book Rejection', 'Data Quality', () => {
    const crossedBids: [number, number][] = [[90005, 1.0]];
    const crossedAsks: [number, number][] = [[90000, 1.0]];
    const book = reconstructOrderBook('BTCUSDT', 1000, 1, crossedBids, crossedAsks);
    if (!book.isCrossed) throw new Error('Failed to detect crossed order book');
  });

  // Test 4: Duplicate & Sequence Gap Validation
  runTest('Duplicate and Sequence Gap Ingestion Check', 'Data Quality', () => {
    const rawJsonl = [
      JSON.stringify({ eventId: 'ev-1', eventType: 'trade', exchangeTimestamp: 1000, sequenceId: 1, price: 90000, size: 1, side: 'buy' }),
      JSON.stringify({ eventId: 'ev-1', eventType: 'trade', exchangeTimestamp: 1000, sequenceId: 1, price: 90000, size: 1, side: 'buy' }), // Duplicate!
      JSON.stringify({ eventId: 'ev-3', eventType: 'trade', exchangeTimestamp: 1050, sequenceId: 5, price: 90002, size: 2, side: 'sell' }), // Gap 2 -> 5
    ];

    const { report } = validateMarketDataBatch(rawJsonl);
    if (report.duplicateEventCount !== 1) throw new Error(`Expected 1 duplicate, got ${report.duplicateEventCount}`);
    if (report.sequenceGapCount === 0) throw new Error('Expected sequence gap to be detected');
  });

  // Test 5: No-Lookahead Invariant in Forward Returns
  runTest('Strict No-Lookahead Forward Return Invariant', 'Research Lab', () => {
    // Create sequential bars with deterministic prices
    const bars = Array.from({ length: 100 }, (_, i) => ({
      timestamp: 1000 + i * 60000,
      timeString: `Bar-${i}`,
      open: 100 + i,
      high: 102 + i,
      low: 99 + i,
      close: 101 + i, // Strictly rising
      volume: 10,
      buyVolume: 7,
      sellVolume: 3,
      signedDelta: 4,
      cumulativeVolumeDelta: 4 * (i + 1),
      tradeCount: 10,
      buyTradeCount: 7,
      sellTradeCount: 3,
      tradeCountImbalance: 0.4,
      orderBookImbalance: 0.2,
      micropriceDelta: 0.1,
      rollingDeltaAcceleration: 0,
      deltaPriceDivergence: 0,
      priceImpactPerVolume: 1,
      flowPersistence: 1,
      marketRegime: 'normal' as const,
    }));

    const result = runResearchExperiment(bars, {
      experimentId: 'exp-test',
      name: 'No Lookahead Test',
      symbol: 'BTCUSDT',
      datasetId: 'ds-test',
      featureName: 'signedDelta',
      thresholdOperator: '>',
      thresholdValue: 0,
      horizon: '1m',
      trainSplitPercent: 70,
      createdAt: Date.now(),
    });

    // Since price is strictly rising (Close[t+1] = Close[t] + 1), forward returns MUST be strictly positive!
    if (result.inSample.hitRate !== 100) throw new Error(`Expected 100% hit rate on monotonic series, got ${result.inSample.hitRate}%`);
    if (result.outOfSample.hitRate !== 100) throw new Error(`Expected 100% out-of-sample hit rate, got ${result.outOfSample.hitRate}%`);
  });

  // Test 6: Frozen Monthly Fisher Implementation Check
  runTest('Frozen Monthly Fisher Invariance', 'Production Baseline', () => {
    const highs = [100, 102, 104, 106, 108, 110, 112, 114, 116, 118, 120, 122];
    const lows = [95, 96, 97, 98, 99, 100, 101, 102, 103, 104, 105, 106];
    const fisher = calculateMonthlyFisher(highs, lows);

    if (fisher.length !== highs.length) throw new Error('Fisher output length mismatch');
    const last = fisher[fisher.length - 1];
    if (isNaN(last.fisher) || isNaN(last.value)) throw new Error('Fisher transform produced NaN');
    if (last.fisher <= 0) throw new Error('Uptrend should produce positive Fisher value');
  });

  // Test 7: Correlation and Statistical Math
  runTest('Pearson Correlation and t-Distribution Limits', 'Statistical Library', () => {
    const x = [1, 2, 3, 4, 5];
    const y = [2, 4, 6, 8, 10]; // Perfect positive correlation
    const r = calculatePearsonCorrelation(x, y);
    if (Math.abs(r - 1.0) > 0.001) throw new Error(`Expected r=1.0, got ${r}`);

    const metrics = computeDistributionMetrics([10, 20, 30, 40, 50]);
    if (metrics.meanReturnBps !== 30) throw new Error(`Expected mean 30, got ${metrics.meanReturnBps}`);
    if (metrics.hitRate !== 100) throw new Error(`Expected hit rate 100%, got ${metrics.hitRate}`);
  });

  return results;
}
