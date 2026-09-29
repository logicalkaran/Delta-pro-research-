/**
 * Delta Research & Indicator Engine V2
 * Market Microstructure & Quantitative Research Type Definitions
 */

export type MarketDataEventType = 'trade' | 'depth_update' | 'depth_snapshot' | 'ticker' | 'funding';

export interface RawMarketEvent {
  eventId: string;
  eventType: MarketDataEventType;
  symbol: string;
  exchangeTimestamp: number; // UTC ms from exchange matching engine
  localReceiveTimestamp: number; // UTC ms when collector captured event
  sequenceId: number;
  data: Record<string, any>;
  isValid: boolean;
  validationErrors?: string[];
}

export interface TradeEvent {
  tradeId: string;
  symbol: string;
  price: number;
  size: number;
  side: 'buy' | 'sell'; // Taker side
  exchangeTimestamp: number;
  localReceiveTimestamp: number;
  isAggressiveBuy: boolean;
  isAggressiveSell: boolean;
  value: number; // price * size
}

export interface BookLevel {
  price: number;
  size: number;
  ordersCount?: number;
}

export interface OrderBookState {
  symbol: string;
  timestamp: number;
  sequenceId: number;
  bids: BookLevel[]; // Sorted descending by price
  asks: BookLevel[]; // Sorted ascending by price
  bestBid: number;
  bestAsk: number;
  midPrice: number;
  spread: number;
  spreadBps: number;
  microprice: number; // Volume-weighted midprice
  bidDepth5: number;
  askDepth5: number;
  depthImbalance5: number; // (bidDepth - askDepth) / (bidDepth + askDepth)
  bidDepth10: number;
  askDepth10: number;
  depthImbalance10: number;
  bidDepth20: number;
  askDepth20: number;
  depthImbalance20: number;
  liquidityConcentration: number; // Ratio of top 3 levels to top 20 levels
  isCrossed: boolean;
}

export interface DeltaBar {
  timestamp: number; // Bar open or close time
  timeString: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  buyVolume: number;
  sellVolume: number;
  signedDelta: number; // buyVolume - sellVolume
  cumulativeVolumeDelta: number; // CVD
  tradeCount: number;
  buyTradeCount: number;
  sellTradeCount: number;
  tradeCountImbalance: number; // (buyTrades - sellTrades) / totalTrades
  orderBookImbalance: number;
  micropriceDelta: number;
  rollingDeltaAcceleration: number;
  deltaPriceDivergence: number; // Normalized divergence score [-1, +1]
  priceImpactPerVolume: number; // bps per 1000 BTC traded
  flowPersistence: number; // Autocorrelation of flow
  marketRegime: MarketRegimeType;
}

export type MarketRegimeType =
  | 'trending_bull'
  | 'trending_bear'
  | 'ranging_choppy'
  | 'high_volatility'
  | 'low_volatility'
  | 'high_liquidity'
  | 'low_liquidity'
  | 'normal';

export interface DataQualityReport {
  totalRecordsProcessed: number;
  validRecordsCount: number;
  rejectedRecordsCount: number;
  missingTimestampCount: number;
  duplicateEventCount: number;
  outOfOrderCount: number;
  sequenceGapCount: number;
  crossedBookCount: number;
  negativeQuantityCount: number;
  maxTimestampDriftMs: number;
  meanTimestampDriftMs: number;
  rejectionLog: {
    timestamp: number;
    sequenceId: number;
    reason: string;
    rawSample: string;
  }[];
  healthScore: number; // 0 - 100
}

export interface ResearchExperimentConfig {
  experimentId: string;
  name: string;
  symbol: string;
  datasetId: string;
  featureName: string;
  thresholdOperator: '>' | '<' | '>=' | '<=' | 'quantile_top' | 'quantile_bottom';
  thresholdValue: number;
  horizon: '1s' | '5s' | '15s' | '30s' | '1m' | '5m' | '15m' | '1h';
  filterRegime?: MarketRegimeType | 'all';
  trainSplitPercent: number; // e.g. 70
  createdAt: number;
}

export interface ExperimentDistributionMetrics {
  sampleCount: number;
  positiveCount: number;
  negativeCount: number;
  hitRate: number; // % of positive forward returns
  meanReturnBps: number;
  medianReturnBps: number;
  stdDevReturnBps: number;
  tStatistic: number;
  pValue: number;
  isStatisticallySignificant: boolean; // p < 0.05
  informationCoefficient: number; // Correlation between feature value & forward return
  maxAdverseExcursionBps: number; // MAE
  maxFavorableExcursionBps: number; // MFE
  sharpeRatioAnnualized: number;
  returnQuantiles: {
    q10: number;
    q25: number;
    q50: number;
    q75: number;
    q90: number;
  };
}

export interface ResearchExperimentResult {
  config: ResearchExperimentConfig;
  inSample: ExperimentDistributionMetrics;
  outOfSample: ExperimentDistributionMetrics;
  baselineZeroSignal: ExperimentDistributionMetrics;
  baselineMomentum: ExperimentDistributionMetrics;
  baselineMonthlyFisher: ExperimentDistributionMetrics;
  validationVerdict: 'INSUFFICIENT_EVIDENCE' | 'WEAK_SIGNAL' | 'STATISTICALLY_SIGNIFICANT' | 'OVERFIT_REJECTED';
  verdictExplanation: string;
  executionTimestamp: number;
}

export type IndicatorLifecycleStatus =
  | 'DRAFT'
  | 'RESEARCHING'
  | 'IN_SAMPLE_VALIDATED'
  | 'OUT_OF_SAMPLE_VALIDATED'
  | 'REJECTED'
  | 'EXPERIMENTAL';

export interface IndicatorDefinition {
  id: string;
  name: string;
  version: string;
  formula: string;
  description: string;
  requiredFields: string[];
  parameters: Record<string, number | string | boolean>;
  calculationTimeframe: string;
  warmupPeriod: number;
  signalDefinition: {
    longCondition: string;
    shortCondition: string;
    exitCondition: string;
  };
  missingDataBehavior: 'interpolate' | 'hold_last' | 'drop_and_warn';
  status: IndicatorLifecycleStatus;
  createdAt: number;
  lastValidatedAt?: number;
  validationMetrics?: {
    inSampleHitRate: number;
    outOfSampleHitRate: number;
    outOfSampleIC: number;
    outOfSamplePValue: number;
    sampleSize: number;
  };
}

/**
 * Frozen Production Strategy Configuration
 * Must remain untouched per project mandate
 */
export interface MonthlyFisherConfig {
  source: 'HL2';
  length: 10;
  alpha: 0.33;
  beta: 0.67;
  status: 'FROZEN_PRODUCTION';
  decisionEngineVersion: 'V1';
}

export const FROZEN_MONTHLY_FISHER: MonthlyFisherConfig = {
  source: 'HL2',
  length: 10,
  alpha: 0.33,
  beta: 0.67,
  status: 'FROZEN_PRODUCTION',
  decisionEngineVersion: 'V1',
};
