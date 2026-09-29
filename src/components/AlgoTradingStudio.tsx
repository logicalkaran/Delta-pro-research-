import React, { useState } from 'react';
import {
  Cpu,
  Play,
  RotateCcw,
  Sparkles,
  TrendingUp,
  TrendingDown,
  Layers,
  ArrowUpRight,
  ArrowDownRight,
  Shield,
  Zap,
  BarChart,
  CheckCircle2,
  DollarSign,
  AlertTriangle,
  Send,
} from 'lucide-react';
import {
  AlgoStrategy,
  BacktestResult,
  Candle,
  Position,
  Ticker,
} from '../types/crypto';
import { runBacktest } from '../utils/backtestEngine';
import { playOrderFilledSound } from '../utils/indicators';

interface AlgoTradingStudioProps {
  currentSymbol: string;
  candles: Candle[];
  markPrice: number;
  onApplyBacktestTradesToChart: (result: BacktestResult) => void;
  positions: Position[];
  onOpenPosition: (pos: Omit<Position, 'id' | 'openedAt' | 'currentPrice' | 'unrealizedPnl' | 'unrealizedPnlPercent'>) => void;
  onClosePosition: (id: string) => void;
  paperBalance: number;
  tickers: Ticker[];
}

const PRESET_STRATEGIES: AlgoStrategy[] = [
  {
    id: 'strat-momentum',
    name: 'Delta Trend-Momentum Ribbon',
    type: 'momentum',
    description: 'Enters long on EMA 20 crossing above EMA 50 with RSI confirmation. Exits on trend reversal or trailing profit.',
    indicators: ['EMA (20)', 'EMA (50)', 'RSI (14)'],
    timeframe: '1h',
    leverage: 10,
    stopLossPercent: 2.5,
    takeProfitPercent: 6.0,
    fastPeriod: 20,
    slowPeriod: 50,
  },
  {
    id: 'strat-reversion',
    name: 'Bollinger Mean-Reversion Scalper',
    type: 'mean_reversion',
    description: 'Fades statistical extremes when candle pierces 2-sigma Bollinger Bands with RSI oversold/overbought.',
    indicators: ['Bollinger Bands (20, 2)', 'RSI (14)'],
    timeframe: '15m',
    leverage: 15,
    stopLossPercent: 1.8,
    takeProfitPercent: 4.2,
    bbStdDev: 2,
  },
  {
    id: 'strat-funding',
    name: 'Delta Funding Arbitrage Harvester',
    type: 'funding_arbitrage',
    description: 'Collects high Delta Exchange 8-hour perpetual funding yields by entering delta-hedged long/short positions.',
    indicators: ['Delta 8h Funding Rate', 'Index Basis'],
    timeframe: '4h',
    leverage: 5,
    stopLossPercent: 3.0,
    takeProfitPercent: 8.5,
  },
  {
    id: 'strat-breakout',
    name: 'Volatility & Volume Breakout',
    type: 'breakout',
    description: 'Catches explosive moves when price penetrates 20-candle high/low with 1.3x volume expansion.',
    indicators: ['Volume Spike (1.3x)', 'Highest High Channel'],
    timeframe: '1h',
    leverage: 8,
    stopLossPercent: 2.2,
    takeProfitPercent: 5.5,
  },
];

export const AlgoTradingStudio: React.FC<AlgoTradingStudioProps> = ({
  currentSymbol,
  candles,
  markPrice,
  onApplyBacktestTradesToChart,
  positions,
  onOpenPosition,
  onClosePosition,
  paperBalance,
  tickers,
}) => {
  const [activeTab, setActiveTab] = useState<'backtest' | 'paper' | 'ai_architect'>('backtest');

  // Strategy & Backtest State
  const [selectedStrategy, setSelectedStrategy] = useState<AlgoStrategy>(PRESET_STRATEGIES[0]);
  const [leverage, setLeverage] = useState<number>(selectedStrategy.leverage || 10);
  const [stopLoss, setStopLoss] = useState<number>(selectedStrategy.stopLossPercent || 2.5);
  const [takeProfit, setTakeProfit] = useState<number>(selectedStrategy.takeProfitPercent || 6.0);
  const [backtestResult, setBacktestResult] = useState<BacktestResult | null>(null);

  // Paper Trading Ticket State
  const [orderSide, setOrderSide] = useState<'LONG' | 'SHORT'>('LONG');
  const [orderLeverage, setOrderLeverage] = useState<number>(10);
  const [orderAmountUsd, setOrderAmountUsd] = useState<number>(1000);

  // AI Strategy Generator State
  const [aiPrompt, setAiPrompt] = useState<string>(
    'Design a high-frequency ETH scalp strategy that exploits funding rate oscillations and Bollinger squeeze'
  );
  const [aiLoading, setAiLoading] = useState(false);
  const [generatedAiStrategy, setGeneratedAiStrategy] = useState<any | null>(null);

  // Run Backtest
  const handleExecuteBacktest = () => {
    const customConfig: AlgoStrategy = {
      ...selectedStrategy,
      leverage,
      stopLossPercent: stopLoss,
      takeProfitPercent: takeProfit,
    };
    const res = runBacktest(candles, customConfig, currentSymbol, paperBalance);
    setBacktestResult(res);
    onApplyBacktestTradesToChart(res);
  };

  // Place Paper Trading Order
  const handlePlaceOrder = () => {
    const margin = orderAmountUsd / orderLeverage;
    if (margin > paperBalance) {
      alert('Insufficient virtual USD balance');
      return;
    }

    const size = orderAmountUsd / markPrice;
    const liqPrice =
      orderSide === 'LONG'
        ? markPrice * (1 - 0.9 / orderLeverage)
        : markPrice * (1 + 0.9 / orderLeverage);

    onOpenPosition({
      symbol: currentSymbol,
      side: orderSide,
      entryPrice: markPrice,
      size: Number(size.toFixed(4)),
      leverage: orderLeverage,
      margin: Number(margin.toFixed(2)),
      liquidationPrice: Number(liqPrice.toFixed(2)),
      takeProfitPrice:
        orderSide === 'LONG' ? markPrice * (1 + takeProfit / 100) : markPrice * (1 - takeProfit / 100),
      stopLossPrice:
        orderSide === 'LONG' ? markPrice * (1 - stopLoss / 100) : markPrice * (1 + stopLoss / 100),
    });

    playOrderFilledSound();
  };

  // Call Gemini AI Strategy Generator
  const handleGenerateAiStrategy = async () => {
    if (!aiPrompt.trim()) return;
    setAiLoading(true);

    try {
      const res = await fetch('/api/gemini/generate-strategy', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          userPrompt: aiPrompt,
          asset: currentSymbol,
          riskProfile: 'Moderate',
          timeframe: selectedStrategy.timeframe || '1h',
        }),
      });

      const data = await res.json();
      if (data.success && data.strategy) {
        setGeneratedAiStrategy(data.strategy);
      }
    } catch (err) {
      console.error('Failed to generate strategy:', err);
    } finally {
      setAiLoading(false);
    }
  };

  const handleApplyAiStrategyToBacktest = () => {
    if (!generatedAiStrategy) return;

    const newStrat: AlgoStrategy = {
      id: `ai-strat-${Date.now()}`,
      name: generatedAiStrategy.strategyName,
      type: 'ai_custom',
      description: generatedAiStrategy.description,
      indicators: generatedAiStrategy.indicators || ['EMA(20)', 'RSI(14)'],
      timeframe: '1h',
      leverage: generatedAiStrategy.riskManagement?.maxLeverage || 10,
      stopLossPercent: generatedAiStrategy.riskManagement?.stopLossPercent || 2.5,
      takeProfitPercent: generatedAiStrategy.riskManagement?.takeProfitPercent || 6.0,
      isCustomAi: true,
    };

    setSelectedStrategy(newStrat);
    setLeverage(newStrat.leverage);
    setStopLoss(newStrat.stopLossPercent);
    setTakeProfit(newStrat.takeProfitPercent);
    setActiveTab('backtest');
  };

  return (
    <div className="flex flex-col h-full bg-[#080c14] select-none text-slate-100 p-3 overflow-y-auto space-y-4">
      {/* Studio Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-xl bg-purple-500/20 border border-purple-500/40 flex items-center justify-center">
            <Cpu className="w-4 h-4 text-purple-400" />
          </div>
          <div>
            <h2 className="font-bold text-sm text-white">Delta Quant Lab & Strategy</h2>
            <p className="text-[11px] text-slate-400">
              Algo backtester, paper executor & Gemini strategy designer
            </p>
          </div>
        </div>

        {/* Paper Balance Badge */}
        <div className="px-2.5 py-1 rounded-xl bg-slate-900 border border-slate-800 text-right font-mono">
          <span className="text-[9px] text-slate-500 block">Paper Equity</span>
          <span className="text-xs font-bold text-emerald-400">
            ${paperBalance.toLocaleString(undefined, { minimumFractionDigits: 2 })}
          </span>
        </div>
      </div>

      {/* Navigation Sub-Tabs */}
      <div className="flex items-center gap-1.5 p-1 bg-[#0d121f] rounded-xl border border-slate-800 text-xs">
        <button
          onClick={() => setActiveTab('backtest')}
          className={`flex-1 py-1.5 rounded-lg font-medium transition-all ${
            activeTab === 'backtest'
              ? 'bg-purple-600 text-white font-bold shadow-md shadow-purple-600/30'
              : 'text-slate-400 hover:text-white'
          }`}
        >
          Strategy Backtester
        </button>
        <button
          onClick={() => setActiveTab('paper')}
          className={`flex-1 py-1.5 rounded-lg font-medium transition-all ${
            activeTab === 'paper'
              ? 'bg-cyan-600 text-white font-bold shadow-md shadow-cyan-600/30'
              : 'text-slate-400 hover:text-white'
          }`}
        >
          Live Paper Terminal ({positions.length})
        </button>
        <button
          onClick={() => setActiveTab('ai_architect')}
          className={`flex-1 py-1.5 rounded-lg font-medium flex items-center justify-center gap-1 transition-all ${
            activeTab === 'ai_architect'
              ? 'bg-amber-600 text-white font-bold shadow-md shadow-amber-600/30'
              : 'text-slate-400 hover:text-white'
          }`}
        >
          <Sparkles className="w-3 h-3 text-amber-300" />
          <span>AI Architect</span>
        </button>
      </div>

      {/* TAB 1: Strategy Backtester */}
      {activeTab === 'backtest' && (
        <div className="space-y-3">
          {/* Strategy Preset Selector */}
          <div className="p-3 bg-[#0d121f] border border-slate-800/80 rounded-2xl space-y-2">
            <span className="text-xs font-mono font-bold text-slate-300 block">
              Select Algorithmic Strategy
            </span>
            <div className="grid grid-cols-2 gap-2">
              {PRESET_STRATEGIES.map((strat) => (
                <button
                  key={strat.id}
                  onClick={() => {
                    setSelectedStrategy(strat);
                    setLeverage(strat.leverage);
                    setStopLoss(strat.stopLossPercent);
                    setTakeProfit(strat.takeProfitPercent);
                  }}
                  className={`p-2.5 rounded-xl border text-left transition-all ${
                    selectedStrategy.id === strat.id
                      ? 'bg-purple-950/40 border-purple-500/60 shadow-sm'
                      : 'bg-[#090d16] border-slate-800/80 hover:border-slate-700'
                  }`}
                >
                  <div className="font-bold text-xs text-white truncate">{strat.name}</div>
                  <div className="text-[10px] text-slate-400 mt-1 line-clamp-2">
                    {strat.description}
                  </div>
                  <div className="mt-2 flex items-center gap-1">
                    {strat.indicators.map((ind, i) => (
                      <span
                        key={i}
                        className="text-[9px] font-mono px-1 py-0.2 rounded bg-slate-800 text-purple-300"
                      >
                        {ind}
                      </span>
                    ))}
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* Parameters Slider & Config */}
          <div className="p-3 bg-[#0d121f] border border-slate-800/80 rounded-2xl space-y-3 text-xs font-mono">
            <span className="text-xs font-bold text-slate-300 block font-sans">
              Risk & Execution Parameters
            </span>

            {/* Leverage Slider */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <span className="text-slate-400 text-[11px]">Delta Leverage:</span>
                <span className="font-bold text-cyan-400">{leverage}x</span>
              </div>
              <input
                type="range"
                min="1"
                max="50"
                value={leverage}
                onChange={(e) => setLeverage(Number(e.target.value))}
                className="w-full accent-cyan-400 cursor-pointer"
              />
            </div>

            {/* Stop Loss & Take Profit */}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-slate-400 text-[10px] block mb-1">Stop Loss (%)</label>
                <input
                  type="number"
                  step="0.1"
                  value={stopLoss}
                  onChange={(e) => setStopLoss(Number(e.target.value))}
                  className="w-full bg-[#090d16] border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-rose-400 font-mono"
                />
              </div>
              <div>
                <label className="text-slate-400 text-[10px] block mb-1">Take Profit (%)</label>
                <input
                  type="number"
                  step="0.1"
                  value={takeProfit}
                  onChange={(e) => setTakeProfit(Number(e.target.value))}
                  className="w-full bg-[#090d16] border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-emerald-400 font-mono"
                />
              </div>
            </div>

            {/* Run Button */}
            <button
              onClick={handleExecuteBacktest}
              className="w-full py-2.5 rounded-xl bg-gradient-to-r from-purple-600 via-indigo-600 to-cyan-600 hover:from-purple-500 hover:to-cyan-500 text-white font-bold text-xs flex items-center justify-center gap-2 shadow-lg shadow-purple-600/30 transition-all font-sans"
            >
              <Play className="w-3.5 h-3.5 fill-current" />
              <span>Simulate Backtest on {candles.length} Delta Candles</span>
            </button>
          </div>

          {/* Backtest Results Card */}
          {backtestResult && (
            <div className="p-3.5 bg-[#0e1424] border border-purple-500/40 rounded-2xl shadow-xl space-y-3 animate-in fade-in duration-300">
              <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                <div>
                  <span className="font-bold text-xs text-white">Backtest Performance</span>
                  <span className="text-[10px] font-mono text-purple-400 block">
                    {backtestResult.strategyName} ({currentSymbol})
                  </span>
                </div>
                <div className="text-right">
                  <span
                    className={`font-mono font-bold text-sm ${
                      backtestResult.totalReturnPercent >= 0 ? 'text-emerald-400' : 'text-rose-400'
                    }`}
                  >
                    {backtestResult.totalReturnPercent >= 0 ? '+' : ''}
                    {backtestResult.totalReturnPercent}% Return
                  </span>
                </div>
              </div>

              {/* 4 Metric Badges */}
              <div className="grid grid-cols-4 gap-1.5 text-center font-mono">
                <div className="p-2 rounded-xl bg-[#090d16] border border-slate-800">
                  <span className="text-[9px] text-slate-500 block">Win Rate</span>
                  <span className="font-bold text-xs text-emerald-400">
                    {backtestResult.winRatePercent}%
                  </span>
                </div>
                <div className="p-2 rounded-xl bg-[#090d16] border border-slate-800">
                  <span className="text-[9px] text-slate-500 block">Profit Factor</span>
                  <span className="font-bold text-xs text-cyan-400">
                    {backtestResult.profitFactor}
                  </span>
                </div>
                <div className="p-2 rounded-xl bg-[#090d16] border border-slate-800">
                  <span className="text-[9px] text-slate-500 block">Max Drawdown</span>
                  <span className="font-bold text-xs text-rose-400">
                    -{backtestResult.maxDrawdownPercent}%
                  </span>
                </div>
                <div className="p-2 rounded-xl bg-[#090d16] border border-slate-800">
                  <span className="text-[9px] text-slate-500 block">Trades</span>
                  <span className="font-bold text-xs text-slate-200">
                    {backtestResult.totalTrades}
                  </span>
                </div>
              </div>

              {/* Recent Trade History in Backtest */}
              <div className="space-y-1">
                <span className="text-[10px] font-mono text-slate-400 block">
                  Simulated Trade Execution Log (Overlaid on Chart)
                </span>
                <div className="space-y-1 max-h-[160px] overflow-y-auto">
                  {backtestResult.trades.slice(0, 10).map((t) => (
                    <div
                      key={t.id}
                      className="p-1.5 rounded-lg bg-[#090d16] border border-slate-800/80 flex items-center justify-between text-[10px] font-mono"
                    >
                      <div className="flex items-center gap-1.5">
                        <span
                          className={`font-bold px-1 rounded ${
                            t.type === 'BUY'
                              ? 'bg-emerald-500/20 text-emerald-400'
                              : 'bg-rose-500/20 text-rose-400'
                          }`}
                        >
                          {t.type}
                        </span>
                        <span className="text-slate-300">${t.entryPrice.toLocaleString()}</span>
                        <span className="text-slate-500">→</span>
                        <span className="text-slate-300">${t.exitPrice.toLocaleString()}</span>
                      </div>
                      <div className="text-right">
                        <span
                          className={`font-bold ${
                            t.pnlPercent >= 0 ? 'text-emerald-400' : 'text-rose-400'
                          }`}
                        >
                          {t.pnlPercent >= 0 ? '+' : ''}
                          {t.pnlPercent}% (${t.pnlUsd})
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* TAB 2: Live Paper Trading Terminal */}
      {activeTab === 'paper' && (
        <div className="space-y-3">
          {/* Order Placement Ticket */}
          <div className="p-3 bg-[#0d121f] border border-slate-800/80 rounded-2xl space-y-3 text-xs font-mono">
            <div className="flex items-center justify-between">
              <span className="font-bold text-white font-sans">
                Execute Simulated Trade ({currentSymbol})
              </span>
              <span className="text-[10px] text-cyan-400">Mark: ${markPrice.toLocaleString()}</span>
            </div>

            {/* Long / Short Toggle */}
            <div className="grid grid-cols-2 gap-2">
              <button
                onClick={() => setOrderSide('LONG')}
                className={`py-2 rounded-xl font-bold font-sans text-xs transition-all ${
                  orderSide === 'LONG'
                    ? 'bg-emerald-500 text-slate-950 shadow-md shadow-emerald-500/30'
                    : 'bg-slate-800 text-slate-400'
                }`}
              >
                BUY / LONG
              </button>
              <button
                onClick={() => setOrderSide('SHORT')}
                className={`py-2 rounded-xl font-bold font-sans text-xs transition-all ${
                  orderSide === 'SHORT'
                    ? 'bg-rose-500 text-white shadow-md shadow-rose-500/30'
                    : 'bg-slate-800 text-slate-400'
                }`}
              >
                SELL / SHORT
              </button>
            </div>

            {/* Leverage and Amount */}
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="text-slate-400 text-[10px] block mb-1">Leverage</label>
                <select
                  value={orderLeverage}
                  onChange={(e) => setOrderLeverage(Number(e.target.value))}
                  className="w-full bg-[#090d16] border border-slate-800 rounded-lg p-1.5 text-xs text-white"
                >
                  <option value={2}>2x</option>
                  <option value={5}>5x</option>
                  <option value={10}>10x</option>
                  <option value={20}>20x</option>
                  <option value={50}>50x (Delta Max)</option>
                </select>
              </div>

              <div>
                <label className="text-slate-400 text-[10px] block mb-1">Position Size ($)</label>
                <input
                  type="number"
                  value={orderAmountUsd}
                  onChange={(e) => setOrderAmountUsd(Number(e.target.value))}
                  className="w-full bg-[#090d16] border border-slate-800 rounded-lg p-1.5 text-xs text-white"
                />
              </div>
            </div>

            {/* Order Calculations */}
            <div className="p-2 rounded-xl bg-[#090d16] border border-slate-800 text-[10px] text-slate-400 space-y-1">
              <div className="flex justify-between">
                <span>Required Margin:</span>
                <span className="text-slate-200">
                  ${(orderAmountUsd / orderLeverage).toFixed(2)} USDT
                </span>
              </div>
              <div className="flex justify-between">
                <span>Estimated Liquidation:</span>
                <span className="text-rose-400">
                  $
                  {(orderSide === 'LONG'
                    ? markPrice * (1 - 0.9 / orderLeverage)
                    : markPrice * (1 + 0.9 / orderLeverage)
                  ).toFixed(2)}
                </span>
              </div>
            </div>

            <button
              onClick={handlePlaceOrder}
              className={`w-full py-2.5 rounded-xl font-bold font-sans text-xs flex items-center justify-center gap-1.5 shadow-lg transition-all ${
                orderSide === 'LONG'
                  ? 'bg-emerald-500 hover:bg-emerald-400 text-slate-950 shadow-emerald-500/30'
                  : 'bg-rose-500 hover:bg-rose-400 text-white shadow-rose-500/30'
              }`}
            >
              <span>Confirm {orderSide} {currentSymbol}</span>
            </button>
          </div>

          {/* Open Positions List */}
          <div className="space-y-2">
            <span className="text-xs font-mono font-bold text-slate-400 block">
              OPEN DELTA POSITIONS ({positions.length})
            </span>

            {positions.length === 0 ? (
              <div className="p-6 bg-[#0c101a] border border-slate-800/80 rounded-2xl text-center text-slate-500 text-xs">
                <Shield className="w-6 h-6 mx-auto mb-2 opacity-30" />
                <p>No active positions open. Place a paper trade above.</p>
              </div>
            ) : (
              positions.map((pos) => {
                const pnl =
                  pos.side === 'LONG'
                    ? (markPrice - pos.entryPrice) * pos.size
                    : (pos.entryPrice - markPrice) * pos.size;
                const pnlPercent = (pnl / pos.margin) * 100;
                const isProfit = pnl >= 0;

                return (
                  <div
                    key={pos.id}
                    className="p-3 rounded-2xl bg-[#0d121f] border border-slate-800/80 space-y-2 text-xs font-mono"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-1.5">
                        <span className="font-bold text-white text-sm">{pos.symbol}</span>
                        <span
                          className={`text-[10px] font-bold px-1.5 py-0.2 rounded ${
                            pos.side === 'LONG'
                              ? 'bg-emerald-500/20 text-emerald-400'
                              : 'bg-rose-500/20 text-rose-400'
                          }`}
                        >
                          {pos.side} {pos.leverage}x
                        </span>
                      </div>
                      <div className="text-right">
                        <span
                          className={`font-bold text-sm ${
                            isProfit ? 'text-emerald-400' : 'text-rose-400'
                          }`}
                        >
                          {isProfit ? '+' : ''}
                          {pnlPercent.toFixed(2)}% (${pnl.toFixed(2)})
                        </span>
                      </div>
                    </div>

                    <div className="grid grid-cols-3 gap-2 text-[10px] text-slate-400 pt-1">
                      <div>
                        <span className="block text-slate-500">Entry</span>
                        <span>${pos.entryPrice.toLocaleString()}</span>
                      </div>
                      <div>
                        <span className="block text-slate-500">Mark</span>
                        <span className="text-cyan-400">${markPrice.toLocaleString()}</span>
                      </div>
                      <div>
                        <span className="block text-slate-500">Liq. Price</span>
                        <span className="text-rose-400">
                          ${pos.liquidationPrice.toLocaleString()}
                        </span>
                      </div>
                    </div>

                    <button
                      onClick={() => onClosePosition(pos.id)}
                      className="w-full py-1.5 rounded-lg bg-slate-800 hover:bg-rose-600 hover:text-white text-slate-300 text-[11px] font-bold transition-colors font-sans"
                    >
                      Market Close Position
                    </button>
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}

      {/* TAB 3: Gemini AI Strategy Architect */}
      {activeTab === 'ai_architect' && (
        <div className="space-y-3">
          <div className="p-3 bg-gradient-to-b from-[#111827] to-[#0d121f] border border-amber-500/40 rounded-2xl shadow-xl space-y-3 text-xs">
            <div className="flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-amber-400" />
              <span className="font-bold text-white text-sm">
                Gemini Quant Strategy Architect
              </span>
            </div>
            <p className="text-slate-300 text-[11px] leading-relaxed">
              Describe your trading idea, edge hypothesis, or market regime. Gemini will architect
              exact entry/exit mathematical criteria, indicator filters, and risk models for Delta
              Exchange.
            </p>

            <textarea
              rows={3}
              value={aiPrompt}
              onChange={(e) => setAiPrompt(e.target.value)}
              placeholder="e.g. Design a conservative ETH options selling strategy during low volatility with Delta hedge"
              className="w-full bg-[#080c14] border border-slate-700 rounded-xl p-2.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-amber-500 font-mono"
            />

            <button
              onClick={handleGenerateAiStrategy}
              disabled={aiLoading}
              className="w-full py-2.5 rounded-xl bg-gradient-to-r from-amber-500 to-orange-500 hover:from-amber-400 hover:to-orange-400 text-slate-950 font-bold text-xs flex items-center justify-center gap-2 shadow-lg shadow-amber-500/20 transition-all disabled:opacity-50"
            >
              <Sparkles className={`w-3.5 h-3.5 ${aiLoading ? 'animate-spin' : ''}`} />
              <span>{aiLoading ? 'Generating Algo Strategy...' : 'Architect Algo Strategy'}</span>
            </button>
          </div>

          {/* Generated AI Strategy Result Card */}
          {generatedAiStrategy && (
            <div className="p-3.5 bg-[#0f172a] border border-amber-500/50 rounded-2xl shadow-xl space-y-3 text-xs font-mono">
              <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                <span className="font-bold text-amber-300 text-sm">
                  {generatedAiStrategy.strategyName}
                </span>
                <button
                  onClick={handleApplyAiStrategyToBacktest}
                  className="px-3 py-1 rounded-lg bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-[11px] flex items-center gap-1 transition-all"
                >
                  <Play className="w-3 h-3 fill-current" />
                  <span>Load into Backtester</span>
                </button>
              </div>

              <p className="text-slate-300 font-sans text-[12px] leading-relaxed">
                {generatedAiStrategy.description}
              </p>

              {/* Rules List */}
              <div className="space-y-1.5">
                <span className="text-[10px] text-emerald-400 font-bold block">Entry Rules:</span>
                {generatedAiStrategy.entryRules?.map((r: string, i: number) => (
                  <div key={i} className="text-[11px] text-slate-300 flex items-start gap-1.5">
                    <span className="text-emerald-400">•</span>
                    <span>{r}</span>
                  </div>
                ))}
              </div>

              <div className="space-y-1.5">
                <span className="text-[10px] text-rose-400 font-bold block">Exit Rules:</span>
                {generatedAiStrategy.exitRules?.map((r: string, i: number) => (
                  <div key={i} className="text-[11px] text-slate-300 flex items-start gap-1.5">
                    <span className="text-rose-400">•</span>
                    <span>{r}</span>
                  </div>
                ))}
              </div>

              {/* Edge */}
              <div className="p-2 rounded-xl bg-amber-950/20 border border-amber-500/30 text-[11px] text-amber-200 font-sans">
                <span className="font-bold block text-amber-400 text-[10px] uppercase font-mono">
                  Delta Exchange Structural Edge:
                </span>
                {generatedAiStrategy.deltaExchangeEdge}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
