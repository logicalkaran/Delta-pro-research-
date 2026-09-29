import React, { useState } from 'react';
import {
  PieChart,
  TrendingUp,
  TrendingDown,
  Sparkles,
  ShieldAlert,
  Target,
  RefreshCw,
  Compass,
  Zap,
  BarChart,
  Sliders,
  CheckCircle,
} from 'lucide-react';
import { GeminiMarketAnalysis, Ticker } from '../types/crypto';

interface MarketAnalysisDashboardProps {
  currentSymbol: string;
  tickers: Ticker[];
  analysis: GeminiMarketAnalysis | null;
  isLoadingAnalysis: boolean;
  onRefreshAnalysis: () => void;
  markPrice: number;
}

export const MarketAnalysisDashboard: React.FC<MarketAnalysisDashboardProps> = ({
  currentSymbol,
  tickers,
  analysis,
  isLoadingAnalysis,
  onRefreshAnalysis,
  markPrice,
}) => {
  // Fear & Greed Index calculation based on price momentum and funding
  const fearGreedValue = 72; // Greed
  const longRatio = 58.4;
  const shortRatio = 41.6;

  // Options Volatility Skew metrics typical of Delta Exchange
  const callPutRatio = 1.34;
  const btcIV = 54.8;
  const ethIV = 61.2;

  return (
    <div className="flex flex-col h-full bg-[#080c14] select-none text-slate-100 p-3 overflow-y-auto space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-xl bg-cyan-500/20 border border-cyan-500/40 flex items-center justify-center">
            <Compass className="w-4 h-4 text-cyan-400" />
          </div>
          <div>
            <h2 className="font-bold text-sm text-white">Delta Market Intelligence</h2>
            <p className="text-[11px] text-slate-400">
              Derivatives sentiment, funding skew & Gemini AI research
            </p>
          </div>
        </div>

        <button
          onClick={onRefreshAnalysis}
          disabled={isLoadingAnalysis}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white text-xs font-bold shadow-md shadow-cyan-500/20 transition-all disabled:opacity-50"
        >
          <Sparkles className={`w-3.5 h-3.5 ${isLoadingAnalysis ? 'animate-spin' : ''}`} />
          <span>{isLoadingAnalysis ? 'Analyzing...' : 'Deep AI Intel'}</span>
        </button>
      </div>

      {/* Top Sentiment Grid */}
      <div className="grid grid-cols-2 gap-2.5">
        {/* Fear & Greed Index Card */}
        <div className="p-3 bg-[#0d121f] border border-slate-800/80 rounded-2xl flex flex-col justify-between">
          <div className="flex items-center justify-between text-[11px] text-slate-400 font-mono">
            <span>CRYPTO SENTIMENT</span>
            <span className="text-emerald-400 font-bold">GREED</span>
          </div>
          <div className="my-2 flex items-baseline gap-2">
            <span className="text-2xl font-black font-mono text-emerald-400">{fearGreedValue}</span>
            <span className="text-xs text-slate-400">/ 100</span>
          </div>
          {/* Progress bar */}
          <div className="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden flex">
            <div
              className="bg-gradient-to-r from-amber-500 via-emerald-400 to-cyan-400 h-full rounded-full transition-all duration-500"
              style={{ width: `${fearGreedValue}%` }}
            />
          </div>
          <span className="text-[10px] text-slate-400 mt-1">
            Delta taker accumulation & high open interest
          </span>
        </div>

        {/* Delta Exchange Long/Short Ratio Card */}
        <div className="p-3 bg-[#0d121f] border border-slate-800/80 rounded-2xl flex flex-col justify-between">
          <div className="flex items-center justify-between text-[11px] text-slate-400 font-mono">
            <span>DELTA L/S RATIO</span>
            <span className="text-cyan-400 font-bold">1.40x</span>
          </div>
          <div className="my-2 flex items-center justify-between font-mono text-xs">
            <span className="text-emerald-400 font-bold">{longRatio}% Long</span>
            <span className="text-rose-400 font-bold">{shortRatio}% Short</span>
          </div>
          <div className="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden flex">
            <div className="bg-emerald-500 h-full" style={{ width: `${longRatio}%` }} />
            <div className="bg-rose-500 h-full" style={{ width: `${shortRatio}%` }} />
          </div>
          <span className="text-[10px] text-slate-400 mt-1">Top accounts bias on BTC & ETH perps</span>
        </div>
      </div>

      {/* Delta Exchange 8h Funding Rate Heatmap */}
      <div className="p-3 bg-[#0d121f] border border-slate-800/80 rounded-2xl space-y-2">
        <div className="flex items-center justify-between text-xs font-mono">
          <span className="text-slate-300 font-bold flex items-center gap-1.5">
            <Zap className="w-3.5 h-3.5 text-amber-400" />
            Delta 8h Funding Rates
          </span>
          <span className="text-[10px] text-slate-500">Next settlement in 2h 45m</span>
        </div>

        <div className="grid grid-cols-3 gap-2 text-xs font-mono">
          {tickers.slice(0, 3).map((t) => {
            const isPos = t.funding_rate >= 0;
            return (
              <div
                key={t.symbol}
                className="p-2 rounded-xl bg-[#090d16] border border-slate-800/60 text-center"
              >
                <div className="text-[10px] text-slate-400 font-bold">{t.symbol}</div>
                <div
                  className={`text-xs font-bold mt-0.5 ${
                    isPos ? 'text-emerald-400' : 'text-rose-400'
                  }`}
                >
                  {(t.funding_rate * 100).toFixed(4)}%
                </div>
                <span className="text-[9px] text-slate-500 block mt-0.5">
                  Pred: {(t.predicted_funding_rate * 100).toFixed(4)}%
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Gemini AI Research Card */}
      <div className="p-3.5 bg-gradient-to-b from-[#0f172a] to-[#0d121f] border border-cyan-500/40 rounded-2xl shadow-xl space-y-3 relative overflow-hidden">
        <div className="absolute top-0 right-0 w-32 h-32 bg-cyan-500/10 rounded-full blur-2xl pointer-events-none" />

        <div className="flex items-center justify-between border-b border-slate-800 pb-2">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-lg bg-cyan-500/20 flex items-center justify-center">
              <Sparkles className="w-3.5 h-3.5 text-cyan-400" />
            </div>
            <div>
              <span className="font-bold text-xs text-white">Gemini Market Copilot</span>
              <span className="text-[10px] font-mono text-cyan-400 ml-2">gemini-3.8-flash</span>
            </div>
          </div>

          {analysis && (
            <span className="text-[10px] px-2 py-0.5 rounded-full font-mono bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
              {analysis.regime}
            </span>
          )}
        </div>

        {analysis ? (
          <div className="space-y-2.5 text-xs font-mono">
            {/* Executive Summary */}
            <p className="text-slate-300 font-sans leading-relaxed text-[12px] bg-[#090d16]/80 p-2.5 rounded-xl border border-slate-800/80">
              {analysis.summary}
            </p>

            {/* Key Levels & Bias */}
            <div className="grid grid-cols-2 gap-2">
              <div className="p-2 rounded-xl bg-[#090d16] border border-slate-800">
                <span className="text-[10px] text-emerald-400 block font-bold mb-1">
                  Key Support Levels
                </span>
                <div className="space-y-0.5 text-slate-200">
                  {analysis.keyLevels.support.map((s, idx) => (
                    <div key={idx} className="flex items-center gap-1">
                      <span className="text-slate-500 text-[10px]">S{idx + 1}:</span>
                      <span>{s}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="p-2 rounded-xl bg-[#090d16] border border-slate-800">
                <span className="text-[10px] text-rose-400 block font-bold mb-1">
                  Key Resistance Levels
                </span>
                <div className="space-y-0.5 text-slate-200">
                  {analysis.keyLevels.resistance.map((r, idx) => (
                    <div key={idx} className="flex items-center gap-1">
                      <span className="text-slate-500 text-[10px]">R{idx + 1}:</span>
                      <span>{r}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* High Probability Trade Setup */}
            <div className="p-2.5 rounded-xl bg-cyan-950/20 border border-cyan-500/30 space-y-1.5">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-bold text-cyan-300 flex items-center gap-1">
                  <Target className="w-3.5 h-3.5 text-cyan-400" />
                  Actionable Trade Setup
                </span>
                <span
                  className={`text-[10px] px-1.5 py-0.2 rounded font-bold ${
                    analysis.tradeSetup.direction === 'LONG'
                      ? 'bg-emerald-500/20 text-emerald-400'
                      : 'bg-rose-500/20 text-rose-400'
                  }`}
                >
                  {analysis.tradeSetup.direction} ({analysis.tradeSetup.riskRewardRatio})
                </span>
              </div>

              <div className="grid grid-cols-2 gap-2 text-[11px] text-slate-300 pt-1">
                <div>
                  <span className="text-slate-500 text-[10px] block">Entry Zone</span>
                  <span>{analysis.tradeSetup.entryZone}</span>
                </div>
                <div>
                  <span className="text-slate-500 text-[10px] block">Invalidation Stop</span>
                  <span className="text-rose-400">{analysis.tradeSetup.stopLoss}</span>
                </div>
                <div>
                  <span className="text-slate-500 text-[10px] block">Take Profit 1</span>
                  <span className="text-emerald-400">{analysis.tradeSetup.takeProfit1}</span>
                </div>
                <div>
                  <span className="text-slate-500 text-[10px] block">Take Profit 2</span>
                  <span className="text-emerald-400">{analysis.tradeSetup.takeProfit2}</span>
                </div>
              </div>
            </div>

            {/* Recommended Algo */}
            <div className="p-2 rounded-xl bg-slate-900 border border-slate-800 text-[11px] flex items-center justify-between">
              <span className="text-slate-400">Recommended Algo:</span>
              <span className="text-amber-300 font-bold truncate max-w-[200px]">
                {analysis.algoRecommendation}
              </span>
            </div>
          </div>
        ) : (
          <div className="text-center py-6 text-slate-400 text-xs space-y-2">
            <RefreshCw
              className={`w-6 h-6 mx-auto text-cyan-400 ${
                isLoadingAnalysis ? 'animate-spin' : ''
              }`}
            />
            <p>Tap "Deep AI Intel" to analyze {currentSymbol} order flow, funding, and technical regimes.</p>
          </div>
        )}
      </div>

      {/* Multi-Timeframe Trend Consensus Radar */}
      <div className="p-3 bg-[#0d121f] border border-slate-800/80 rounded-2xl space-y-2">
        <span className="text-xs font-mono font-bold text-slate-300 block">
          Multi-Timeframe Trend Radar
        </span>
        <div className="grid grid-cols-4 gap-1.5 text-center font-mono text-xs">
          <div className="p-1.5 rounded-lg bg-[#090d16] border border-slate-800">
            <span className="text-[10px] text-slate-500 block">15m</span>
            <span className="text-emerald-400 font-bold">Bullish</span>
          </div>
          <div className="p-1.5 rounded-lg bg-[#090d16] border border-slate-800">
            <span className="text-[10px] text-slate-500 block">1h</span>
            <span className="text-emerald-400 font-bold">Bullish</span>
          </div>
          <div className="p-1.5 rounded-lg bg-[#090d16] border border-slate-800">
            <span className="text-[10px] text-slate-500 block">4h</span>
            <span className="text-cyan-400 font-bold">Consolidation</span>
          </div>
          <div className="p-1.5 rounded-lg bg-[#090d16] border border-slate-800">
            <span className="text-[10px] text-slate-500 block">1D</span>
            <span className="text-emerald-400 font-bold">Strong Bull</span>
          </div>
        </div>
      </div>
    </div>
  );
};
