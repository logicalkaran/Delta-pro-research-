export interface Ticker {
  symbol: string;
  name: string;
  underlying_asset: 'BTC' | 'ETH' | 'SOL' | string;
  contract_type: 'perpetual_futures' | 'call_options' | 'put_options' | string;
  mark_price: number;
  index_price: number;
  close: number;
  open_24h: number;
  high_24h: number;
  low_24h: number;
  change_24h_percent: number;
  volume_24h: number;
  turnover_24h: number;
  open_interest: number;
  funding_rate: number;
  predicted_funding_rate: number;
  quotes: {
    best_bid: number;
    best_ask: number;
  };
}

export interface Candle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface OrderBookItem {
  price: number;
  size: number;
  total: number;
}

export interface OrderBook {
  bids: OrderBookItem[];
  asks: OrderBookItem[];
  spread: number;
  spreadPercent: number;
}

export interface TradeTick {
  id: string;
  price: number;
  size: number;
  side: 'buy' | 'sell';
  time: string;
}

export type AlertCondition =
  | 'crosses_above'
  | 'crosses_below'
  | 'change_percent_above'
  | 'change_percent_below'
  | 'rsi_overbought'
  | 'rsi_oversold'
  | 'funding_rate_above';

export interface AlertRule {
  id: string;
  symbol: string;
  condition: AlertCondition;
  targetValue: number;
  note: string;
  soundEnabled: boolean;
  active: boolean;
  createdAt: number;
  triggeredAt?: number;
}

export interface AlertNotification {
  id: string;
  ruleId: string;
  symbol: string;
  title: string;
  message: string;
  timestamp: number;
  price: number;
}

export interface AlgoStrategy {
  id: string;
  name: string;
  type: 'momentum' | 'mean_reversion' | 'funding_arbitrage' | 'breakout' | 'grid' | 'ai_custom';
  description: string;
  indicators: string[];
  timeframe: string;
  leverage: number;
  stopLossPercent: number;
  takeProfitPercent: number;
  fastPeriod?: number;
  slowPeriod?: number;
  rsiThreshold?: number;
  bbStdDev?: number;
  isCustomAi?: boolean;
}

export interface BacktestTrade {
  id: string;
  type: 'BUY' | 'SELL';
  entryTime: number;
  exitTime: number;
  entryPrice: number;
  exitPrice: number;
  pnlPercent: number;
  pnlUsd: number;
  reason: string;
}

export interface BacktestResult {
  strategyName: string;
  symbol: string;
  totalReturnPercent: number;
  winRatePercent: number;
  profitFactor: number;
  maxDrawdownPercent: number;
  totalTrades: number;
  winningTrades: number;
  losingTrades: number;
  trades: BacktestTrade[];
}

export interface Position {
  id: string;
  symbol: string;
  side: 'LONG' | 'SHORT';
  entryPrice: number;
  currentPrice: number;
  size: number; // in contracts or coin
  leverage: number;
  margin: number;
  liquidationPrice: number;
  unrealizedPnl: number;
  unrealizedPnlPercent: number;
  takeProfitPrice?: number;
  stopLossPrice?: number;
  openedAt: number;
}

export interface GeminiMarketAnalysis {
  regime: string;
  sentiment: string;
  keyLevels: {
    support: string[];
    resistance: string[];
  };
  orderFlowBias: string;
  tradeSetup: {
    direction: 'LONG' | 'SHORT' | 'DELTA_NEUTRAL';
    entryZone: string;
    takeProfit1: string;
    takeProfit2: string;
    stopLoss: string;
    riskRewardRatio: string;
  };
  algoRecommendation: string;
  summary: string;
}
