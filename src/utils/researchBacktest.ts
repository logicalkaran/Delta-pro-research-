import { Candle } from '../types/crypto';
import { ema, rsi } from './advancedIndicators';

export type ResearchStrategy = 'ema_cross' | 'rsi_reversal' | 'range_breakout';
export interface BacktestConfig { strategy: ResearchStrategy; feeBps: number; slippageBps: number; }
export interface BacktestTradeResult { direction: 'LONG' | 'SHORT'; entryTime: number; exitTime: number; entryPrice: number; exitPrice: number; grossReturnPct: number; netReturnPct: number; }
export interface SegmentResult { startIndex: number; endIndex: number; trades: BacktestTradeResult[]; totalReturnPct: number; winRatePct: number; profitFactor: number; maxDrawdownPct: number; }
export interface WalkForwardResult { fullSample: SegmentResult; folds: SegmentResult[]; compoundedOosReturnPct: number; totalOosTrades: number; worstFoldDrawdownPct: number; }

function makeSignals(candles: Candle[], strategy: ResearchStrategy): number[] {
  const close = candles.map(c => c.close), signal = Array(candles.length).fill(0);
  if (strategy === 'ema_cross') {
    const fast = ema(close, 12), slow = ema(close, 26);
    for (let i = 1; i < candles.length; i++) {
      if (fast[i - 1] != null && slow[i - 1] != null && fast[i] != null && slow[i] != null) {
        if (fast[i - 1]! <= slow[i - 1]! && fast[i]! > slow[i]!) signal[i] = 1;
        else if (fast[i - 1]! >= slow[i - 1]! && fast[i]! < slow[i]!) signal[i] = -1;
      }
    }
  } else if (strategy === 'rsi_reversal') {
    const values = rsi(close, 14);
    for (let i = 1; i < values.length; i++) {
      if (values[i - 1] != null && values[i] != null) {
        if (values[i - 1]! <= 30 && values[i]! > 30) signal[i] = 1;
        else if (values[i - 1]! >= 70 && values[i]! < 70) signal[i] = -1;
      }
    }
  } else {
    for (let i = 20; i < candles.length; i++) {
      const prior = candles.slice(i - 20, i);
      const upper = Math.max(...prior.map(c => c.high)), lower = Math.min(...prior.map(c => c.low));
      if (candles[i].close > upper) signal[i] = 1;
      else if (candles[i].close < lower) signal[i] = -1;
    }
  }
  return signal;
}

function runSegment(candles: Candle[], signals: number[], start: number, end: number, costBps: number): SegmentResult {
  const trades: BacktestTradeResult[] = [];
  let position: { direction: 1 | -1; entryPrice: number; entryTime: number } | null = null;
  const closePosition = (price: number, time: number) => {
    if (!position) return;
    const gross = position.direction * (price - position.entryPrice) / position.entryPrice;
    const net = gross - (2 * costBps / 10000);
    trades.push({ direction: position.direction === 1 ? 'LONG' : 'SHORT', entryTime: position.entryTime, exitTime: time, entryPrice: position.entryPrice, exitPrice: price, grossReturnPct: gross * 100, netReturnPct: net * 100 });
    position = null;
  };
  for (let i = Math.max(0, start); i < Math.min(end, candles.length - 1); i++) {
    const next = candles[i + 1], s = signals[i];
    if (position && s === -position.direction) closePosition(next.open, next.time);
    if (!position && s !== 0) position = { direction: s as 1 | -1, entryPrice: next.open, entryTime: next.time };
  }
  if (position && end >= start) closePosition(candles[Math.min(end, candles.length - 1)].close, candles[Math.min(end, candles.length - 1)].time);
  let equity = 1, peak = 1, maxDD = 0;
  for (const trade of trades) { equity *= Math.max(0, 1 + trade.netReturnPct / 100); peak = Math.max(peak, equity); maxDD = Math.max(maxDD, peak > 0 ? (peak - equity) / peak * 100 : 0); }
  const wins = trades.filter(t => t.netReturnPct > 0), losses = trades.filter(t => t.netReturnPct < 0);
  const grossWin = wins.reduce((s,t)=>s+t.netReturnPct,0), grossLoss = Math.abs(losses.reduce((s,t)=>s+t.netReturnPct,0));
  return { startIndex: start, endIndex: end, trades, totalReturnPct: (equity - 1) * 100, winRatePct: trades.length ? wins.length / trades.length * 100 : 0, profitFactor: grossLoss ? grossWin / grossLoss : grossWin ? Infinity : 0, maxDrawdownPct: maxDD };
}

export function runWalkForwardResearch(candles: Candle[], config: BacktestConfig, foldCount = 4): WalkForwardResult {
  const signals = makeSignals(candles, config.strategy);
  const costBps = Math.max(0, config.feeBps) + Math.max(0, config.slippageBps);
  const last = candles.length - 1;
  const fullSample = runSegment(candles, signals, 0, last, costBps);
  const firstOos = Math.floor(candles.length * 0.5);
  const available = Math.max(0, last - firstOos + 1);
  const foldTotal = available >= 4 ? Math.min(foldCount, Math.floor(available / 4)) : 0;
  const foldSize = foldTotal ? Math.floor(available / foldTotal) : 0;
  const folds: SegmentResult[] = Array.from({ length: foldTotal }, (_, i) => {
    const start = firstOos + i * foldSize;
    const end = i === foldTotal - 1 ? last : Math.min(last, start + foldSize - 1);
    return runSegment(candles, signals, start, end, costBps);
  });
  const compounded = folds.reduce((equity, fold) => equity * Math.max(0, 1 + fold.totalReturnPct / 100), 1);
  return { fullSample, folds, compoundedOosReturnPct: (compounded - 1) * 100, totalOosTrades: folds.reduce((s,f)=>s+f.trades.length,0), worstFoldDrawdownPct: folds.length ? Math.max(...folds.map(f=>f.maxDrawdownPct)) : 0 };
}
