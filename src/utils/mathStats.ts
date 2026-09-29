/**
 * Pure Statistical & Quantitative Mathematical Library
 * Implements rigorous sample statistics, hypothesis testing, t-distributions, and correlations.
 */

export function calculateMean(values: number[]): number {
  if (values.length === 0) return 0;
  return values.reduce((sum, v) => sum + v, 0) / values.length;
}

export function calculateMedian(values: number[]): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  if (sorted.length % 2 !== 0) {
    return sorted[mid];
  }
  return (sorted[mid - 1] + sorted[mid]) / 2;
}

export function calculateVariance(values: number[], isSample: boolean = true): number {
  if (values.length < 2) return 0;
  const mean = calculateMean(values);
  const sumSq = values.reduce((sum, v) => sum + Math.pow(v - mean, 2), 0);
  return sumSq / (values.length - (isSample ? 1 : 0));
}

export function calculateStdDev(values: number[], isSample: boolean = true): number {
  return Math.sqrt(calculateVariance(values, isSample));
}

export function calculateQuantiles(values: number[]): {
  q10: number;
  q25: number;
  q50: number;
  q75: number;
  q90: number;
} {
  if (values.length === 0) {
    return { q10: 0, q25: 0, q50: 0, q75: 0, q90: 0 };
  }
  const sorted = [...values].sort((a, b) => a - b);
  const getP = (p: number) => {
    const idx = (sorted.length - 1) * p;
    const lower = Math.floor(idx);
    const upper = Math.ceil(idx);
    const weight = idx - lower;
    if (lower === upper) return sorted[lower];
    return sorted[lower] * (1 - weight) + sorted[upper] * weight;
  };

  return {
    q10: Number(getP(0.1).toFixed(3)),
    q25: Number(getP(0.25).toFixed(3)),
    q50: Number(getP(0.5).toFixed(3)),
    q75: Number(getP(0.75).toFixed(3)),
    q90: Number(getP(0.9).toFixed(3)),
  };
}

/**
 * Pearson Correlation Coefficient (r)
 */
export function calculatePearsonCorrelation(x: number[], y: number[]): number {
  const n = Math.min(x.length, y.length);
  if (n < 3) return 0;

  let sumX = 0;
  let sumY = 0;
  let sumXY = 0;
  let sumX2 = 0;
  let sumY2 = 0;

  for (let i = 0; i < n; i++) {
    sumX += x[i];
    sumY += y[i];
    sumXY += x[i] * y[i];
    sumX2 += x[i] * x[i];
    sumY2 += y[i] * y[i];
  }

  const numerator = n * sumXY - sumX * sumY;
  const denominator = Math.sqrt((n * sumX2 - sumX * sumX) * (n * sumY2 - sumY * sumY));
  if (denominator === 0 || isNaN(denominator)) return 0;

  const r = numerator / denominator;
  return Number(Math.max(-1, Math.min(1, r)).toFixed(4));
}

/**
 * Two-tailed p-value approximation from Student's t-statistic
 * Uses series expansion for degrees of freedom df = n - 1
 */
export function calculateStudentTPValue(t: number, df: number): number {
  if (df <= 0) return 1.0;
  const absT = Math.abs(t);
  if (absT === 0) return 1.0;

  // Use Abramowitz and Stegun / Hill approximation for t-dist p-value
  const x = df / (df + absT * absT);
  const a = df / 2;
  const b = 0.5;

  // Beta function approximation
  const pOneTailed = 0.5 * incompleteBeta(x, a, b);
  const pTwoTailed = Math.min(1.0, Math.max(0.000001, 2 * pOneTailed));
  return Number(pTwoTailed.toFixed(5));
}

function incompleteBeta(x: number, a: number, b: number): number {
  if (x <= 0) return 0;
  if (x >= 1) return 1;

  // Continued fraction approximation for regularized incomplete beta function
  const maxIterations = 60;
  const epsilon = 1e-10;

  const factor = Math.exp(logGamma(a + b) - logGamma(a) - logGamma(b) + a * Math.log(x) + b * Math.log(1 - x));

  let c = 1.0;
  let d = 1.0 - (a + b) * x / (a + 1.0);
  if (Math.abs(d) < epsilon) d = epsilon;
  d = 1.0 / d;
  let result = d;

  for (let m = 1; m <= maxIterations; m++) {
    // Even step
    let num = (m * (b - m) * x) / ((a + 2 * m - 1) * (a + 2 * m));
    d = 1.0 + num * d;
    if (Math.abs(d) < epsilon) d = epsilon;
    c = 1.0 + num / c;
    if (Math.abs(c) < epsilon) c = epsilon;
    d = 1.0 / d;
    result *= d * c;

    // Odd step
    num = -((a + m) * (a + b + m) * x) / ((a + 2 * m) * (a + 2 * m + 1));
    d = 1.0 + num * d;
    if (Math.abs(d) < epsilon) d = epsilon;
    c = 1.0 + num / c;
    if (Math.abs(c) < epsilon) c = epsilon;
    d = 1.0 / d;
    const delta = d * c;
    result *= delta;

    if (Math.abs(delta - 1.0) < epsilon) break;
  }

  return Math.min(1.0, Math.max(0.0, (factor / a) * result));
}

function logGamma(z: number): number {
  const c = [
    57.1562356658629235, -59.5979603554754912, 14.1360979747417471,
    -0.491913816097620199, 0.339946499848118887e-4, 0.465236289270485756e-4,
    -0.983744753048795646e-4, 0.158088703224377394e-3, -0.210264441724104883e-3,
    0.217439618115212643e-3, -0.16431810653676389e-3, 0.844182239838527433e-4,
    -0.261908384015814087e-4, 0.368991826595316234e-5,
  ];
  let sum = 0.999999999999997092;
  for (let i = 0; i < c.length; i++) {
    sum += c[i] / (z + i + 1);
  }
  const t = z + c.length - 0.5;
  return 0.5 * Math.log(2 * Math.PI) + (z + 0.5) * Math.log(t) - t + Math.log(sum);
}

/**
 * Compute forward-return distribution statistics and hypothesis test
 */
export function computeDistributionMetrics(
  returnsBps: number[],
  featureValues: number[] = []
) {
  const sampleCount = returnsBps.length;
  if (sampleCount === 0) {
    return {
      sampleCount: 0,
      positiveCount: 0,
      negativeCount: 0,
      hitRate: 0,
      meanReturnBps: 0,
      medianReturnBps: 0,
      stdDevReturnBps: 0,
      tStatistic: 0,
      pValue: 1.0,
      isStatisticallySignificant: false,
      informationCoefficient: 0,
      maxAdverseExcursionBps: 0,
      maxFavorableExcursionBps: 0,
      sharpeRatioAnnualized: 0,
      returnQuantiles: { q10: 0, q25: 0, q50: 0, q75: 0, q90: 0 },
    };
  }

  const positiveCount = returnsBps.filter((r) => r > 0).length;
  const negativeCount = returnsBps.filter((r) => r < 0).length;
  const hitRate = Number(((positiveCount / sampleCount) * 100).toFixed(2));

  const meanReturnBps = Number(calculateMean(returnsBps).toFixed(3));
  const medianReturnBps = Number(calculateMedian(returnsBps).toFixed(3));
  const stdDevReturnBps = Number(calculateStdDev(returnsBps).toFixed(3));

  // One-sample t-test: H0: mean = 0
  const standardError = stdDevReturnBps / Math.sqrt(sampleCount);
  const tStatistic = standardError > 0 ? Number((meanReturnBps / standardError).toFixed(3)) : 0;
  const pValue = sampleCount > 2 ? calculateStudentTPValue(tStatistic, sampleCount - 1) : 1.0;
  const isStatisticallySignificant = sampleCount >= 30 && pValue < 0.05;

  // Information Coefficient (IC)
  let informationCoefficient = 0;
  if (featureValues.length === returnsBps.length && sampleCount >= 3) {
    informationCoefficient = calculatePearsonCorrelation(featureValues, returnsBps);
  }

  // MAE and MFE
  const maxAdverseExcursionBps = Number(Math.min(...returnsBps).toFixed(3));
  const maxFavorableExcursionBps = Number(Math.max(...returnsBps).toFixed(3));

  // Annualized Sharpe approximation (assuming 1m/1h horizon basis, roughly scaled)
  const sharpeRatioAnnualized =
    stdDevReturnBps > 0
      ? Number(((meanReturnBps / stdDevReturnBps) * Math.sqrt(252 * 24)).toFixed(2))
      : 0;

  const returnQuantiles = calculateQuantiles(returnsBps);

  return {
    sampleCount,
    positiveCount,
    negativeCount,
    hitRate,
    meanReturnBps,
    medianReturnBps,
    stdDevReturnBps,
    tStatistic,
    pValue,
    isStatisticallySignificant,
    informationCoefficient,
    maxAdverseExcursionBps,
    maxFavorableExcursionBps,
    sharpeRatioAnnualized,
    returnQuantiles,
  };
}
