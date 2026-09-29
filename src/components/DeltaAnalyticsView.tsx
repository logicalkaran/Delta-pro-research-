import React, { useState } from 'react';
import {
  BarChart3,
  TrendingUp,
  TrendingDown,
  Info,
  Zap,
  Activity,
  ArrowUpRight,
  ArrowDownRight,
  HelpCircle,
} from 'lucide-react';
import { DeltaBar } from '../types/microstructure';

interface DeltaAnalyticsViewProps {
  bars: DeltaBar[];
}

export const DeltaAnalyticsView: React.FC<DeltaAnalyticsViewProps> = ({ bars }) => {
  const [showFormulaModal, setShowFormulaModal] = useState<boolean>(false);
  const [selectedBar, setSelectedBar] = useState<DeltaBar | null>(null);

  const activeBars = bars.slice(-40);
  const latestBar = bars.length > 0 ? bars[bars.length - 1] : null;

  // Max values for chart height scaling
  const maxAbsDelta = Math.max(...activeBars.map((b) => Math.abs(b.signedDelta)), 1.0);
  const maxCVD = Math.max(...activeBars.map((b) => b.cumulativeVolumeDelta));
  const minCVD = Math.min(...activeBars.map((b) => b.cumulativeVolumeDelta));
  const cvdRange = Math.max(0.1, maxCVD - minCVD);

  return (
    <div className="p-4 sm:p-6 space-y-5 max-w-7xl mx-auto text-slate-100 font-mono">
      {/* Header Banner */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 p-4 rounded-2xl bg-[#0d121f] border border-slate-800">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-cyan-500/20 border border-cyan-500/40 flex items-center justify-center">
            <BarChart3 className="w-4 h-4 text-cyan-400" />
          </div>
          <div>
            <h2 className="font-bold text-sm text-white font-sans">
              Delta Analytics & Cumulative Volume Delta (CVD)
            </h2>
            <p className="text-[11px] text-slate-400 font-sans">
              Aggressive trade flow imbalance, volume delta acceleration, and price-delta absorption divergence
            </p>
          </div>
        </div>

        <button
          onClick={() => setShowFormulaModal(true)}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-cyan-300 font-sans text-xs font-semibold border border-cyan-500/30 transition-all"
        >
          <HelpCircle className="w-3.5 h-3.5" />
          <span>Formula & Units Panel</span>
        </button>
      </div>

      {/* 4 Feature Metrics Cards */}
      {latestBar && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
          {/* Signed Delta */}
          <div className="p-3.5 bg-[#0d121f] rounded-2xl border border-slate-800 space-y-1">
            <div className="flex items-center justify-between text-slate-400">
              <span>LATEST SIGNED DELTA</span>
              <span className={latestBar.signedDelta >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
                {latestBar.signedDelta >= 0 ? 'NET BUY' : 'NET SELL'}
              </span>
            </div>
            <div className={`text-xl font-bold ${latestBar.signedDelta >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
              {latestBar.signedDelta > 0 ? '+' : ''}{latestBar.signedDelta.toFixed(2)} BTC
            </div>
            <div className="text-[11px] text-slate-400">
              Buy: {latestBar.buyVolume.toFixed(2)} • Sell: {latestBar.sellVolume.toFixed(2)}
            </div>
          </div>

          {/* Cumulative Volume Delta */}
          <div className="p-3.5 bg-[#0d121f] rounded-2xl border border-slate-800 space-y-1">
            <div className="flex items-center justify-between text-slate-400">
              <span>CUMULATIVE CVD</span>
              <span className="text-cyan-400 font-bold">Aggregate</span>
            </div>
            <div className={`text-xl font-bold ${latestBar.cumulativeVolumeDelta >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
              {latestBar.cumulativeVolumeDelta > 0 ? '+' : ''}{latestBar.cumulativeVolumeDelta.toFixed(2)} BTC
            </div>
            <div className="text-[11px] text-slate-400">Total Session Delta Trend</div>
          </div>

          {/* Delta Acceleration */}
          <div className="p-3.5 bg-[#0d121f] rounded-2xl border border-slate-800 space-y-1">
            <div className="flex items-center justify-between text-slate-400">
              <span>FLOW ACCELERATION</span>
              <span className={latestBar.rollingDeltaAcceleration >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
                d(Delta)/dt
              </span>
            </div>
            <div className={`text-xl font-bold ${latestBar.rollingDeltaAcceleration >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
              {latestBar.rollingDeltaAcceleration > 0 ? '+' : ''}{latestBar.rollingDeltaAcceleration.toFixed(2)}
            </div>
            <div className="text-[11px] text-slate-400">5-bar rolling acceleration surge</div>
          </div>

          {/* Divergence Flag */}
          <div className="p-3.5 bg-[#0d121f] rounded-2xl border border-slate-800 space-y-1">
            <div className="flex items-center justify-between text-slate-400">
              <span>PRICE-DELTA DIVERGENCE</span>
              <span className="text-purple-400 font-bold">Absorption</span>
            </div>
            <div className="text-lg font-bold">
              {latestBar.deltaPriceDivergence === 1 ? (
                <span className="text-emerald-400 flex items-center gap-1">
                  <ArrowUpRight className="w-4 h-4" /> Bullish Absorption
                </span>
              ) : latestBar.deltaPriceDivergence === -1 ? (
                <span className="text-rose-400 flex items-center gap-1">
                  <ArrowDownRight className="w-4 h-4" /> Bearish Exhaustion
                </span>
              ) : (
                <span className="text-slate-400">Flow-Price Aligned</span>
              )}
            </div>
            <div className="text-[11px] text-slate-400">
              Impact: {latestBar.priceImpactPerVolume.toFixed(2)} bps / unit
            </div>
          </div>
        </div>
      )}

      {/* Visual CVD & Signed Delta Bars Component */}
      <div className="p-4 rounded-2xl bg-[#0d121f] border border-slate-800 space-y-3">
        <div className="flex items-center justify-between border-b border-slate-800 pb-2">
          <span className="font-bold text-xs text-white font-sans flex items-center gap-2">
            <TrendingUp className="w-3.5 h-3.5 text-cyan-400" />
            Signed Volume Delta & Cumulative Volume Delta (CVD) Stream
          </span>
          <span className="text-xs text-slate-400">Last 40 Observations</span>
        </div>

        {/* Visual Dual-Bar Representation */}
        <div className="h-64 w-full flex items-end gap-1.5 pt-6 pb-2 overflow-x-auto">
          {activeBars.map((b) => {
            const isPos = b.signedDelta >= 0;
            const deltaHeightPct = Math.min(100, (Math.abs(b.signedDelta) / maxAbsDelta) * 85);
            const cvdNormalized = ((b.cumulativeVolumeDelta - minCVD) / cvdRange) * 100;

            return (
              <div
                key={b.timestamp}
                onClick={() => setSelectedBar(b)}
                className="flex-1 min-w-[14px] flex flex-col items-center justify-end h-full relative cursor-pointer group"
              >
                {/* CVD Dot on Trend Line */}
                <div
                  className="w-1.5 h-1.5 rounded-full bg-cyan-300 absolute z-20 transition-all group-hover:scale-150"
                  style={{ bottom: `${cvdNormalized}%` }}
                  title={`CVD: ${b.cumulativeVolumeDelta.toFixed(2)}`}
                />

                {/* Signed Delta Bar */}
                <div
                  className={`w-full rounded-t transition-all ${
                    isPos
                      ? 'bg-emerald-500/80 group-hover:bg-emerald-400'
                      : 'bg-rose-500/80 group-hover:bg-rose-400'
                  }`}
                  style={{ height: `${Math.max(4, deltaHeightPct)}%` }}
                />

                {/* Hover Tooltip */}
                <div className="absolute -top-14 left-1/2 -translate-x-1/2 hidden group-hover:flex flex-col items-center bg-[#07090e] border border-slate-700 p-1.5 rounded text-[10px] whitespace-nowrap z-30 shadow-xl pointer-events-none">
                  <span className="text-white font-bold">${b.close.toLocaleString()}</span>
                  <span className={isPos ? 'text-emerald-400' : 'text-rose-400'}>
                    Delta: {isPos ? '+' : ''}{b.signedDelta.toFixed(2)} BTC
                  </span>
                  <span className="text-cyan-400">CVD: {b.cumulativeVolumeDelta.toFixed(2)}</span>
                </div>
              </div>
            );
          })}
        </div>

        <div className="flex items-center justify-between text-[11px] text-slate-500 pt-1 border-t border-slate-800">
          <div className="flex items-center gap-4">
            <span className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-sm bg-emerald-500"></span> Positive Delta (Aggressive Buys)
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-sm bg-rose-500"></span> Negative Delta (Aggressive Sells)
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-cyan-300"></span> Cumulative Volume Delta (CVD) Line
            </span>
          </div>
          <span>Hover or tap bar for exact values</span>
        </div>
      </div>

      {/* Selected Bar Details Inspector */}
      {selectedBar && (
        <div className="p-3.5 rounded-2xl bg-[#090d16] border border-cyan-500/40 grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
          <div>
            <span className="text-slate-500 block text-[10px]">TIME / PRICE</span>
            <span className="text-white font-bold">{selectedBar.timeString} • ${selectedBar.close.toLocaleString()}</span>
          </div>
          <div>
            <span className="text-slate-500 block text-[10px]">BUY / SELL TRADES</span>
            <span className="text-slate-300">{selectedBar.buyTradeCount} Buys • {selectedBar.sellTradeCount} Sells</span>
          </div>
          <div>
            <span className="text-slate-500 block text-[10px]">FLOW ACCELERATION</span>
            <span className={selectedBar.rollingDeltaAcceleration >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
              {selectedBar.rollingDeltaAcceleration > 0 ? '+' : ''}{selectedBar.rollingDeltaAcceleration.toFixed(3)}
            </span>
          </div>
          <div>
            <span className="text-slate-500 block text-[10px]">PRICE IMPACT</span>
            <span className="text-cyan-300">{selectedBar.priceImpactPerVolume.toFixed(2)} bps / BTC</span>
          </div>
        </div>
      )}

      {/* Indicator Information & Formulas Modal */}
      {showFormulaModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="w-full max-w-xl bg-[#0d121f] border border-cyan-500/50 rounded-2xl shadow-2xl p-5 space-y-4 font-sans text-xs">
            <div className="flex items-center justify-between border-b border-slate-800 pb-2">
              <span className="font-bold text-sm text-white flex items-center gap-2">
                <Info className="w-4 h-4 text-cyan-400" />
                Delta Microstructure Formulas & Units
              </span>
              <button
                onClick={() => setShowFormulaModal(false)}
                className="text-xs text-slate-400 hover:text-white"
              >
                Close
              </button>
            </div>

            <div className="space-y-3 font-mono text-[11px] text-slate-300">
              <div className="p-3 bg-[#080c14] rounded-xl border border-slate-800">
                <span className="text-cyan-400 font-bold block mb-1">1. Signed Volume Delta</span>
                <code>SignedDelta = Volume_Buy_Taker - Volume_Sell_Taker</code>
                <p className="text-slate-400 font-sans text-[11px] mt-1">
                  Unit: Base Currency (BTC). Positive indicates aggressive buying into limit asks; negative indicates aggressive market selling into limit bids.
                </p>
              </div>

              <div className="p-3 bg-[#080c14] rounded-xl border border-slate-800">
                <span className="text-cyan-400 font-bold block mb-1">2. Cumulative Volume Delta (CVD)</span>
                <code>CVD_t = CVD_(t-1) + SignedDelta_t</code>
                <p className="text-slate-400 font-sans text-[11px] mt-1">
                  Unit: Cumulative Base Currency (BTC). Tracks persistent institutional inventory accumulation vs distribution across the trading session.
                </p>
              </div>

              <div className="p-3 bg-[#080c14] rounded-xl border border-slate-800">
                <span className="text-cyan-400 font-bold block mb-1">3. Trade Delta vs Order-Book Delta Distinction</span>
                <p className="text-slate-300 font-sans text-[11px] leading-relaxed">
                  <strong>Crucial Quantitative Rule:</strong> Trade volume delta reflects filled aggressive taker flow. Order-book delta reflects standing passive limit liquidity. They are mathematically distinct and should never be conflated.
                </p>
              </div>

              <div className="p-3 bg-[#080c14] rounded-xl border border-slate-800">
                <span className="text-cyan-400 font-bold block mb-1">4. Price Impact per Unit Delta</span>
                <code>Impact = (Price_t - Price_(t-1)) / abs(SignedDelta_t) * 10,000 (bps)</code>
                <p className="text-slate-400 font-sans text-[11px] mt-1">
                  Unit: Basis points per unit volume. Measures order book liquidity resilience and slippage elasticity.
                </p>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
