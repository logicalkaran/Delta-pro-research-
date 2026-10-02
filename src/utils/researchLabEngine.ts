import {
  DeltaBar,
  ResearchExperimentConfig,
  ResearchExperimentResult,
  ExperimentDistributionMetrics,
} from '../types/microstructure';
import { computeDistributionMetrics } from './mathStats';
import { calculateMonthlyFisher } from './monthlyFisherEngine';

/**
 * Quantitative Research Laboratory Engine
 * Conducts forward-return predictive validation without lookahead leakage.
 */

export function runResearchExperiment(
  bars: DeltaBar[],
  config: ResearchExperimentConfig
): ResearchExperimentResult {
  const n = bars.length;
  if (n < 40) {
    const emptyMetrics = computeDistributionMetrics([]);
    return {
      config,
      inSample: emptyMetrics,
      outOfSample: emptyMetrics,
      baselineZeroSignal: emptyMetrics,
      baselineMomentum: emptyMetrics,
      baselineMonthlyFisher: emptyMetrics,
      validationVerdict: 'INSUFFICIENT_EVIDENCE',
      verdictExplanation: `Insufficient data points (${n} bars). Minimum 40 bars required for statistically meaningful train/test validation.`,
      executionTimestamp: Date.now(),
    };
  }

  // DeltaBar research data is minute-based. Sub-minute horizons require tick/event data.
  const emptyMetrics = computeDistributionMetrics([]);
  if (['1s', '5s', '15s', '30s'].includes(config.horizon)) {
    return {
      config, inSample: emptyMetrics, outOfSample: emptyMetrics,
      baselineZeroSignal: emptyMetrics, baselineMomentum: emptyMetrics,
      baselineMonthlyFisher: emptyMetrics, validationVerdict: 'INSUFFICIENT_EVIDENCE',
      verdictExplanation: `The selected ${config.horizon} horizon cannot be resolved from 1-minute DeltaBars. Import timestamped tick data and use an event-time research path.`,
      executionTimestamp: Date.now(),
    };
  }
  const horizonBars = config.horizon === '1m' ? 1 : config.horizon === '5m' ? 5 : config.horizon === '15m' ? 15 : 60;
  if (horizonBars > n * 0.25) {
    return {
      config, inSample: emptyMetrics, outOfSample: emptyMetrics,
      baselineZeroSignal: emptyMetrics, baselineMomentum: emptyMetrics,
      baselineMonthlyFisher: emptyMetrics, validationVerdict: 'INSUFFICIENT_EVIDENCE',
      verdictExplanation: `The requested ${config.horizon} horizon consumes at least 25% of the available ${n}-bar dataset. Add more history; the engine will not silently shorten the requested horizon.`,
      executionTimestamp: Date.now(),
    };
  }

  // Calculate forward return in basis points for each bar:
  // Forward return at t = (Close[t + horizon] - Close[t]) / Close[t] * 10,000 bps
  const observations: {
    index: number;
    timestamp: number;
    featureValue: number;
    conditionTriggered: boolean;
    forwardReturnBps: number;
    momentumSignal: boolean;
    fisherSignal: boolean;
    regime: string;
  }[] = [];

  // Compute Monthly Fisher baseline series
  const highs = bars.map((b) => b.high);
  const lows = bars.map((b) => b.low);
  const fisherResults = calculateMonthlyFisher(highs, lows);

  for (let i = 0; i < n - horizonBars; i++) {
    const b = bars[i];
    const targetBar = bars[i + horizonBars];
    const forwardReturnBps = ((targetBar.close - b.close) / b.close) * 10000;

    // Extract feature value
    let featVal = 0;
    switch (config.featureName) {
      case 'signedDelta':
        featVal = b.signedDelta;
        break;
      case 'cumulativeVolumeDelta':
        featVal = b.cumulativeVolumeDelta;
        break;
      case 'tradeCountImbalance':
        featVal = b.tradeCountImbalance;
        break;
      case 'deltaPriceDivergence':
        featVal = b.deltaPriceDivergence;
        break;
      case 'rollingDeltaAcceleration':
        featVal = b.rollingDeltaAcceleration;
        break;
      case 'priceImpactPerVolume':
        featVal = b.priceImpactPerVolume;
        break;
      case 'orderBookImbalance':
        featVal = b.orderBookImbalance;
        break;
      default:
        featVal = b.signedDelta;
    }

    // Condition trigger check
    let conditionTriggered = false;
    if (config.thresholdOperator === '>') {
      conditionTriggered = featVal > config.thresholdValue;
    } else if (config.thresholdOperator === '<') {
      conditionTriggered = featVal < config.thresholdValue;
    } else if (config.thresholdOperator === '>=') {
      conditionTriggered = featVal >= config.thresholdValue;
    } else if (config.thresholdOperator === '<=') {
      conditionTriggered = featVal <= config.thresholdValue;
    } else {
      conditionTriggered = Math.abs(featVal) >= config.thresholdValue;
    }

    // Regime filter if applied
    if (config.filterRegime && config.filterRegime !== 'all') {
      if (b.marketRegime !== config.filterRegime) {
        conditionTriggered = false;
      }
    }

    const prevBar = i > 0 ? bars[i - 1] : b;
    const momentumSignal = b.close > prevBar.close;
    const fisherSignal = fisherResults[i]?.direction === 'LONG';

    observations.push({
      index: i,
      timestamp: b.timestamp,
      featureValue: featVal,
      conditionTriggered,
      forwardReturnBps: Number(forwardReturnBps.toFixed(3)),
      momentumSignal,
      fisherSignal,
      regime: b.marketRegime,
    });
  }

  // Chronological Train/Test Split (Strictly Time-Ordered: No Shuffling!)
  const splitIndex = Math.floor(observations.length * (config.trainSplitPercent / 100));
  const inSampleObs = observations.slice(0, splitIndex);
  const outOfSampleObs = observations.slice(splitIndex);

  // In-Sample conditioning
  const inSampleTriggered = inSampleObs.filter((o) => o.conditionTriggered);
  const inSampleReturns = inSampleTriggered.map((o) => o.forwardReturnBps);
  const inSampleFeatures = inSampleTriggered.map((o) => o.featureValue);
  const inSampleMetrics = computeDistributionMetrics(inSampleReturns, inSampleFeatures);

  // Out-of-Sample conditioning
  const outOfSampleTriggered = outOfSampleObs.filter((o) => o.conditionTriggered);
  const outOfSampleReturns = outOfSampleTriggered.map((o) => o.forwardReturnBps);
  const outOfSampleFeatures = outOfSampleTriggered.map((o) => o.featureValue);
  const outOfSampleMetrics = computeDistributionMetrics(outOfSampleReturns, outOfSampleFeatures);

  // Baseline 1: Unconditional Zero-Signal (all OOS observations)
  const baselineZeroSignal = computeDistributionMetrics(outOfSampleObs.map((o) => o.forwardReturnBps));

  // Baseline 2: Simple Price Momentum
  const baselineMomentum = computeDistributionMetrics(
    outOfSampleObs.filter((o) => o.momentumSignal).map((o) => o.forwardReturnBps)
  );

  // Baseline 3: Frozen Monthly Fisher
  const baselineMonthlyFisher = computeDistributionMetrics(
    outOfSampleObs.filter((o) => o.fisherSignal).map((o) => o.forwardReturnBps)
  );

  // Scientific Validation Verdict
  let validationVerdict: ResearchExperimentResult['validationVerdict'] = 'WEAK_SIGNAL';
  let verdictExplanation = '';

  if (outOfSampleMetrics.sampleCount < 25) {
    validationVerdict = 'INSUFFICIENT_EVIDENCE';
    verdictExplanation = `Out-of-sample sample size (${outOfSampleMetrics.sampleCount}) is below minimum statistical threshold (N >= 25). Cannot accept hypothesis without more test observations.`;
  } else if (inSampleMetrics.isStatisticallySignificant && outOfSampleMetrics.hitRate < 48) {
    validationVerdict = 'OVERFIT_REJECTED';
    verdictExplanation = `In-sample performance (hit rate ${inSampleMetrics.hitRate}%, p=${inSampleMetrics.pValue}) collapsed out-of-sample (hit rate ${outOfSampleMetrics.hitRate}%). Significant evidence of overfitting.`;
  } else if (
    outOfSampleMetrics.isStatisticallySignificant &&
    outOfSampleMetrics.hitRate >= 53.5 &&
    outOfSampleMetrics.meanReturnBps > baselineZeroSignal.meanReturnBps + 2
  ) {
    validationVerdict = 'STATISTICALLY_SIGNIFICANT';
    verdictExplanation = `Hypothesis validated out-of-sample: Hit rate ${outOfSampleMetrics.hitRate}%, t-stat ${outOfSampleMetrics.tStatistic}, p-value ${outOfSampleMetrics.pValue} (< 0.05). Outperformed zero-signal baseline by +${(outOfSampleMetrics.meanReturnBps - baselineZeroSignal.meanReturnBps).toFixed(2)} bps.`;
  } else {
    validationVerdict = 'WEAK_SIGNAL';
    verdictExplanation = `Out-of-sample hit rate is ${outOfSampleMetrics.hitRate}%, but p-value is ${outOfSampleMetrics.pValue} (>= 0.05). Fails null hypothesis rejection at the 95% confidence level.`;
  }

  return {
    config,
    inSample: inSampleMetrics,
    outOfSample: outOfSampleMetrics,
    baselineZeroSignal,
    baselineMomentum,
    baselineMonthlyFisher,
    validationVerdict,
    verdictExplanation,
    executionTimestamp: Date.now(),
  };
}
