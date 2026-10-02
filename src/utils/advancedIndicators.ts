import { Candle } from '../types/crypto';

export type Series = (number | null)[];

const empty = (n: number): Series => Array(n).fill(null);
const mean = (xs: number[]) => xs.reduce((a, b) => a + b, 0) / xs.length;

export function sma(values: number[], period: number): Series {
  const out = empty(values.length);
  if (!Number.isInteger(period) || period < 1) return out;
  for (let i = period - 1; i < values.length; i++) out[i] = mean(values.slice(i - period + 1, i + 1));
  return out;
}

export function ema(values: number[], period: number): Series {
  const out = empty(values.length);
  if (!Number.isInteger(period) || period < 1 || values.length < period) return out;
  const k = 2 / (period + 1);
  let prev = mean(values.slice(0, period));
  out[period - 1] = prev;
  for (let i = period; i < values.length; i++) { prev = values[i] * k + prev * (1 - k); out[i] = prev; }
  return out;
}

export function rsi(values: number[], period = 14): Series {
  const out = empty(values.length);
  if (values.length <= period || period < 1) return out;
  let gain = 0, loss = 0;
  for (let i = 1; i <= period; i++) { const d = values[i] - values[i - 1]; gain += Math.max(d, 0); loss += Math.max(-d, 0); }
  let ag = gain / period, al = loss / period;
  out[period] = al === 0 ? (ag === 0 ? 50 : 100) : 100 - 100 / (1 + ag / al);
  for (let i = period + 1; i < values.length; i++) {
    const d = values[i] - values[i - 1]; ag = (ag * (period - 1) + Math.max(d, 0)) / period; al = (al * (period - 1) + Math.max(-d, 0)) / period;
    out[i] = al === 0 ? (ag === 0 ? 50 : 100) : 100 - 100 / (1 + ag / al);
  }
  return out;
}

export function atr(candles: Candle[], period = 14): Series {
  const tr = candles.map((c, i) => i === 0 ? c.high - c.low : Math.max(c.high - c.low, Math.abs(c.high - candles[i - 1].close), Math.abs(c.low - candles[i - 1].close)));
  const out = empty(candles.length);
  if (candles.length < period || period < 1) return out;
  let value = mean(tr.slice(0, period)); out[period - 1] = value;
  for (let i = period; i < tr.length; i++) { value = (value * (period - 1) + tr[i]) / period; out[i] = value; }
  return out;
}

export function macd(values: number[]): { macd: Series; signal: Series; histogram: Series } {
  const fast = ema(values, 12), slow = ema(values, 26), line = empty(values.length);
  for (let i = 0; i < values.length; i++) if (fast[i] !== null && slow[i] !== null) line[i] = fast[i]! - slow[i]!;
  const signal = empty(values.length);
  const first = line.findIndex(v => v !== null);
  const signalStart = first + 8;
  if (first >= 0 && signalStart < line.length) {
    let previous = mean(line.slice(first, signalStart + 1).map(v => v ?? 0));
    signal[signalStart] = previous;
    for (let i = signalStart + 1; i < line.length; i++) {
      previous = (line[i] ?? 0) * (2 / 10) + previous * (8 / 10);
      signal[i] = line[i] === null ? null : previous;
    }
  }
  const histogram = line.map((v, i) => v === null || signal[i] === null ? null : v - signal[i]!);
  return { macd: line, signal, histogram };
}

export function dmi(candles: Candle[], period = 14): { plusDI: Series; minusDI: Series; adx: Series } {
  const n = candles.length, plusDI = empty(n), minusDI = empty(n), adxSeries = empty(n);
  const tr = Array(n).fill(0), plusDM = Array(n).fill(0), minusDM = Array(n).fill(0), dx = empty(n);
  for (let i = 1; i < n; i++) {
    const up = candles[i].high - candles[i - 1].high, down = candles[i - 1].low - candles[i].low;
    plusDM[i] = up > down && up > 0 ? up : 0;
    minusDM[i] = down > up && down > 0 ? down : 0;
    tr[i] = Math.max(candles[i].high - candles[i].low, Math.abs(candles[i].high - candles[i - 1].close), Math.abs(candles[i].low - candles[i - 1].close));
  }
  if (!Number.isInteger(period) || period < 1 || n < period * 2 + 1) return { plusDI, minusDI, adx: adxSeries };
  let trSmooth = 0, plusSmooth = 0, minusSmooth = 0;
  for (let i = 1; i <= period; i++) { trSmooth += tr[i]; plusSmooth += plusDM[i]; minusSmooth += minusDM[i]; }
  for (let i = period; i < n; i++) {
    if (i > period) {
      trSmooth = trSmooth - trSmooth / period + tr[i];
      plusSmooth = plusSmooth - plusSmooth / period + plusDM[i];
      minusSmooth = minusSmooth - minusSmooth / period + minusDM[i];
    }
    plusDI[i] = trSmooth ? 100 * plusSmooth / trSmooth : 0;
    minusDI[i] = trSmooth ? 100 * minusSmooth / trSmooth : 0;
    const sum = plusDI[i]! + minusDI[i]!;
    dx[i] = sum ? 100 * Math.abs(plusDI[i]! - minusDI[i]!) / sum : 0;
  }
  const firstAdx = period * 2 - 1;
  if (firstAdx < n) {
    const seed = dx.slice(period, firstAdx + 1);
    if (seed.every(v => v !== null)) adxSeries[firstAdx] = mean(seed as number[]);
    for (let i = firstAdx + 1; i < n; i++) {
      if (dx[i] !== null && adxSeries[i - 1] !== null) adxSeries[i] = (adxSeries[i - 1]! * (period - 1) + dx[i]!) / period;
    }
  }
  return { plusDI, minusDI, adx: adxSeries };
}

export function adx(candles: Candle[], period = 14): Series {
  return dmi(candles, period).adx;
}

export function vwap(candles: Candle[]): Series {
  let pv = 0, volume = 0;
  return candles.map(c => { const typical = (c.high + c.low + c.close) / 3; pv += typical * c.volume; volume += c.volume; return volume > 0 ? pv / volume : null; });
}

export function realizedVolatility(candles: Candle[], period = 20): Series {
  const returns = candles.map((c, i) => i ? Math.log(c.close / candles[i - 1].close) : 0);
  const out = empty(candles.length);
  for (let i = period; i < candles.length; i++) {
    const xs = returns.slice(i - period + 1, i + 1), avg = mean(xs);
    out[i] = Math.sqrt(xs.reduce((s, x) => s + (x - avg) ** 2, 0) / (xs.length - 1)) * Math.sqrt(period) * 100;
  }
  return out;
}

export function relativeVolume(candles: Candle[], period = 20): Series {
  const out = empty(candles.length);
  for (let i = period; i < candles.length; i++) {
    const avg = mean(candles.slice(i - period, i).map(c => c.volume));
    out[i] = avg > 0 ? candles[i].volume / avg : null;
  }
  return out;
}

export function validateCandleSeries(candles: Candle[]) {
  let invalidOHLC = 0, invalidValues = 0, duplicateTimes = 0, nonMonotonic = 0, gaps = 0;
  const seen = new Set<number>();
  const deltas: number[] = [];
  for (let i = 0; i < candles.length; i++) {
    const c = candles[i];
    if (![c.time, c.open, c.high, c.low, c.close, c.volume].every(Number.isFinite) || Math.min(c.open, c.high, c.low, c.close) <= 0 || c.volume < 0) invalidValues++;
    if (c.high < Math.max(c.open, c.close, c.low) || c.low > Math.min(c.open, c.close, c.high)) invalidOHLC++;
    if (seen.has(c.time)) duplicateTimes++; seen.add(c.time);
    if (i && c.time <= candles[i - 1].time) nonMonotonic++;
    if (i && c.time > candles[i - 1].time) deltas.push(c.time - candles[i - 1].time);
  }
  const sorted = [...deltas].sort((a, b) => a - b), step = sorted.length ? sorted[Math.floor(sorted.length / 2)] : 0;
  if (step > 0) for (const d of deltas) if (d > step * 1.5) gaps++;
  return { rows: candles.length, invalidOHLC, invalidValues, duplicateTimes, nonMonotonic, detectedGaps: gaps, medianIntervalMs: step };
}
