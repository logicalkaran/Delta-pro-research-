import assert from 'node:assert/strict';
import { sma, ema, rsi, atr, macd, adx, dmi, vwap, relativeVolume, realizedVolatility, validateCandleSeries } from '../src/utils/advancedIndicators';
import type { Candle } from '../src/types/crypto';
import { generateSyntheticMicrostructureData } from '../src/utils/syntheticDataGenerator';
import { runResearchExperiment } from '../src/utils/researchLabEngine';
import type { ResearchExperimentConfig } from '../src/types/microstructure';
import { runWalkForwardResearch } from '../src/utils/researchBacktest';

const candles: Candle[] = Array.from({ length: 80 }, (_, i) => {
  const close = 100 + i * 0.5 + Math.sin(i / 3);
  return { time: 1_700_000_000_000 + i * 60_000, open: close - 0.2, high: close + 0.8, low: close - 0.8, close, volume: 10 + i };
});
assert.equal(sma([1, 2, 3, 4], 3)[2], 2);
assert.equal(ema([1, 2, 3], 3)[2], 2);
assert.ok((rsi(candles.map(c => c.close))[79] ?? 0) > 50);
assert.ok((atr(candles)[79] ?? 0) > 0);
assert.ok(macd(candles.map(c => c.close)).histogram[79] !== null);
assert.ok((adx(candles)[79] ?? 0) >= 0);
assert.ok((dmi(candles).plusDI[79] ?? 0) >= 0 && (dmi(candles).minusDI[79] ?? 0) >= 0);
assert.ok((dmi(candles).adx[79] ?? 0) >= 0);
assert.ok((vwap(candles)[79] ?? 0) > 0);
assert.ok((relativeVolume(candles)[79] ?? 0) > 0);
assert.ok((realizedVolatility(candles)[79] ?? 0) >= 0);
const quality = validateCandleSeries(candles);
assert.equal(quality.invalidOHLC, 0);
assert.equal(quality.invalidValues, 0);
assert.equal(quality.duplicateTimes, 0);
assert.equal(quality.nonMonotonic, 0);
const researchBars = generateSyntheticMicrostructureData(240, 100000).deltaBars;
const researchConfig: ResearchExperimentConfig = {
  experimentId: 'test-minute', name: 'minute horizon smoke', symbol: 'BTCUSDT', datasetId: 'SYNTHETIC-TEST',
  featureName: 'signedDelta', thresholdOperator: '>', thresholdValue: 0, horizon: '1m',
  filterRegime: 'all', trainSplitPercent: 70, createdAt: Date.now(),
};
const minuteResult = runResearchExperiment(researchBars, researchConfig);
assert.notEqual(minuteResult.validationVerdict, 'INSUFFICIENT_EVIDENCE');
const subMinuteResult = runResearchExperiment(researchBars, { ...researchConfig, horizon: '5s' });
assert.equal(subMinuteResult.validationVerdict, 'INSUFFICIENT_EVIDENCE');
assert.match(subMinuteResult.verdictExplanation, /tick data/);
const oscillating: Candle[] = Array.from({ length: 120 }, (_, i) => {
  const close = 100 + 10 * Math.sin(i * 0.3);
  return { time: 1_700_000_000_000 + i * 60_000, open: close, high: close + 0.5, low: close - 0.5, close, volume: 100 };
});
const noCost = runWalkForwardResearch(oscillating, { strategy: 'ema_cross', feeBps: 0, slippageBps: 0 });
const withCosts = runWalkForwardResearch(oscillating, { strategy: 'ema_cross', feeBps: 5, slippageBps: 3 });
assert.equal(withCosts.folds.length, 4);
assert.ok(withCosts.totalOosTrades > 0);
assert.ok(withCosts.folds.every(f => f.trades.every(t => t.netReturnPct < t.grossReturnPct)));
assert.ok(withCosts.compoundedOosReturnPct <= noCost.compoundedOosReturnPct);
console.log('Walk-forward cost model PASS', JSON.stringify({ folds: withCosts.folds.length, oosTrades: withCosts.totalOosTrades, costAdjustedReturn: withCosts.compoundedOosReturnPct }));
console.log('Research horizon validation PASS', JSON.stringify({ minute: minuteResult.validationVerdict, subMinute: subMinuteResult.validationVerdict }));
console.log('Indicator validation PASS', JSON.stringify({ candles: quality.rows, quality, lastRSI: rsi(candles.map(c => c.close))[79], lastATR: atr(candles)[79], lastADX: adx(candles)[79] }));
