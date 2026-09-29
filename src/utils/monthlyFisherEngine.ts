import { FROZEN_MONTHLY_FISHER, MonthlyFisherConfig } from '../types/microstructure';

export interface FisherBarResult {
  hl2: number;
  value: number;
  fisher: number;
  signal: number;
  direction: 'LONG' | 'SHORT' | 'NEUTRAL';
}

/**
 * Frozen Production Strategy: Monthly Fisher
 * Source: HL2, Length: 10, Alpha: 0.33, Beta: 0.67
 *
 * NOTE: This implementation is frozen per quantitative compliance rules.
 * Do not alter parameters or formulas.
 */
export function calculateMonthlyFisher(
  highs: number[],
  lows: number[],
  config: MonthlyFisherConfig = FROZEN_MONTHLY_FISHER
): FisherBarResult[] {
  const n = Math.min(highs.length, lows.length);
  const results: FisherBarResult[] = [];
  if (n === 0) return results;

  const length = config.length; // 10
  const alpha = config.alpha; // 0.33
  const beta = config.beta; // 0.67

  let prevVal1 = 0;
  let prevFisher = 0;

  for (let i = 0; i < n; i++) {
    const hl2 = (highs[i] + lows[i]) / 2;

    if (i < length - 1) {
      results.push({
        hl2,
        value: 0,
        fisher: 0,
        signal: 0,
        direction: 'NEUTRAL',
      });
      continue;
    }

    // Rolling Min/Max over length
    let maxH = -Infinity;
    let minL = Infinity;
    for (let j = 0; j < length; j++) {
      if (highs[i - j] > maxH) maxH = highs[i - j];
      if (lows[i - j] < minL) minL = lows[i - j];
    }

    const range = maxH - minL;
    let val1 = 0;
    if (range > 0) {
      const rawNormalized = (hl2 - minL) / range - 0.5;
      val1 = alpha * 2 * rawNormalized + beta * prevVal1;
    } else {
      val1 = beta * prevVal1;
    }

    // Clamp boundary to prevent log domain singularity
    val1 = Math.max(-0.999, Math.min(0.999, val1));

    // Fisher Transform
    const fisher = 0.5 * Math.log((1 + val1) / (1 - val1)) + 0.5 * prevFisher;

    // Decision Engine V1 rule: cross thresholds
    let direction: 'LONG' | 'SHORT' | 'NEUTRAL' = 'NEUTRAL';
    if (fisher > 0.5 && prevFisher <= 0.5) {
      direction = 'LONG';
    } else if (fisher < -0.5 && prevFisher >= -0.5) {
      direction = 'SHORT';
    } else if (fisher > 0) {
      direction = 'LONG';
    } else if (fisher < 0) {
      direction = 'SHORT';
    }

    results.push({
      hl2: Number(hl2.toFixed(2)),
      value: Number(val1.toFixed(4)),
      fisher: Number(fisher.toFixed(4)),
      signal: Number(prevFisher.toFixed(4)),
      direction,
    });

    prevVal1 = val1;
    prevFisher = fisher;
  }

  return results;
}
