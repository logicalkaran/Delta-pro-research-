import React, { useState } from 'react';
import {
  FlaskConical,
  Play,
  RotateCcw,
  CheckCircle2,
  AlertTriangle,
  Info,
  Sliders,
  TrendingUp,
  BarChart2,
  ShieldAlert,
} from 'lucide-react';
import {
  DeltaBar,
  ResearchExperimentConfig,
  ResearchExperimentResult,
  MarketRegimeType,
} from '../types/microstructure';
import { runResearchExperiment } from '../utils/researchLabEngine';

interface ResearchLabViewProps {
  bars: DeltaBar[];
  datasetId: string;
  symbol: string;
  onSaveExperimentResult: (res: ResearchExperimentResult) => void;
  latestResult: ResearchExperimentResult | null;
}

export const ResearchLabView: React.FC<ResearchLabViewProps> = ({
  bars,
  datasetId,
  symbol,
  onSaveExperimentResult,
  latestResult,
}) => {
  const [featureName, setFeatureName] = useState<string>('signedDelta');
  const [thresholdOperator, setThresholdOperator] = useState<'>' | '<' | '>=' | '<='>('>');
  const [thresholdValue, setThresholdValue] = useState<number>(2.0);
  const [horizon, setHorizon] = useState<ResearchExperimentConfig['horizon']>('5m');
  const [filterRegime, setFilterRegime] = useState<MarketRegimeType | 'all'>('all');
  const [trainSplitPercent, setTrainSplitPercent] = useState<number>(70);
  const [experimentName, setExperimentName] = useState<string>('Aggressive Buy Delta > 2.0 BTC (5m Forward Return)');

  const handleRunExperiment = () => {
    const config: ResearchExperimentConfig = {
      experimentId: `exp-${Date.now()}`,
      name: experimentName || `${featureName} ${thresholdOperator} ${thresholdValue} [${horizon}]`,
      symbol,
      datasetId,
      featureName,
      thresholdOperator,
      thresholdValue,
      horizon,
      filterRegime,
      trainSplitPercent,
      createdAt: Date.now(),
    };

    const res = runResearchExperiment(bars, config);
    onSaveExperimentResult(res);
  };

  const activeResult = latestResult;

  return (
    <div className="p-4 sm:p-6 space-y-5 max-w-7xl mx-auto text-slate-100 font-mono">
      {/* Module Title Banner */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 p-4 rounded-2xl bg-[#0d121f] border border-slate-800">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-purple-500/20 border border-purple-500/40 flex items-center justify-center">
            <FlaskConical className="w-4 h-4 text-purple-400" />
          </div>
          <div>
            <h2 className="font-bold text-sm text-white font-sans">
              Quantitative Hypothesis Testing & Predictive Lab
            </h2>
            <p className="text-[11px] text-slate-400 font-sans">
              Test whether order flow features have statistically meaningful forward-return edge without lookahead bias
            </p>
          </div>
        </div>

        <button
          onClick={handleRunExperiment}
          className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-cyan-500 via-blue-600 to-indigo-600 hover:from-cyan-400 hover:to-indigo-500 text-white font-bold font-sans text-xs shadow-lg shadow-cyan-500/25 transition-all"
        >
          <Play className="w-4 h-4 fill-current" />
          <span>Execute Hypothesis Test</span>
        </button>
      </div>

      {/* Experiment Parameters Configuration Grid */}
      <div className="p-4 rounded-2xl bg-[#0d121f] border border-slate-800 space-y-4">
        <span className="font-bold text-xs text-white block font-sans">
          Experiment Specification & Conditioning
        </span>

        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 text-xs">
          {/* Feature Selector */}
          <div>
            <label className="text-[10px] text-slate-400 block mb-1">MICROSTRUCTURE FEATURE</label>
            <select
              value={featureName}
              onChange={(e) => setFeatureName(e.target.value)}
              className="w-full bg-[#080c14] border border-slate-700 rounded-xl px-2.5 py-1.5 text-xs text-cyan-300 focus:outline-none focus:border-cyan-500"
            >
              <option value="signedDelta">Signed Volume Delta (BTC)</option>
              <option value="cumulativeVolumeDelta">Cumulative Volume Delta (CVD)</option>
              <option value="tradeCountImbalance">Trade Count Imbalance</option>
              <option value="orderBookImbalance">L10 Order-Book Imbalance</option>
              <option value="deltaPriceDivergence">Price-Delta Divergence</option>
              <option value="rollingDeltaAcceleration">Rolling Delta Acceleration</option>
              <option value="priceImpactPerVolume">Price Impact per Unit</option>
            </select>
          </div>

          {/* Condition Operator & Threshold */}
          <div>
            <label className="text-[10px] text-slate-400 block mb-1">TRIGGER CONDITION</label>
            <div className="flex gap-2">
              <select
                value={thresholdOperator}
                onChange={(e) => setThresholdOperator(e.target.value as any)}
                className="w-20 bg-[#080c14] border border-slate-700 rounded-xl px-2 py-1.5 text-xs text-white focus:outline-none"
              >
                <option value=">">&gt;</option>
                <option value="<">&lt;</option>
                <option value=">=">&gt;=</option>
                <option value="<=">&lt;=</option>
              </select>
              <input
                type="number"
                step="0.1"
                value={thresholdValue}
                onChange={(e) => setThresholdValue(Number(e.target.value))}
                className="flex-1 bg-[#080c14] border border-slate-700 rounded-xl px-2.5 py-1.5 text-xs text-white focus:outline-none"
              />
            </div>
          </div>

          {/* Forward Return Horizon */}
          <div>
            <label className="text-[10px] text-slate-400 block mb-1">FORWARD RETURN HORIZON</label>
            <select
              value={horizon}
              onChange={(e) => setHorizon(e.target.value as any)}
              className="w-full bg-[#080c14] border border-slate-700 rounded-xl px-2.5 py-1.5 text-xs text-white focus:outline-none focus:border-cyan-500"
            >
              <option value="1s">1 second (High-Freq)</option>
              <option value="5s">5 seconds</option>
              <option value="15s">15 seconds</option>
              <option value="30s">30 seconds</option>
              <option value="1m">1 minute (Bar Close)</option>
              <option value="5m">5 minutes (Medium Horizon)</option>
              <option value="15m">15 minutes</option>
              <option value="1h">1 hour</option>
            </select>
          </div>

          {/* Market Regime Filter */}
          <div>
            <label className="text-[10px] text-slate-400 block mb-1">REGIME CONDITIONAL FILTER</label>
            <select
              value={filterRegime}
              onChange={(e) => setFilterRegime(e.target.value as any)}
              className="w-full bg-[#080c14] border border-slate-700 rounded-xl px-2.5 py-1.5 text-xs text-white focus:outline-none focus:border-cyan-500"
            >
              <option value="all">All Regimes (Unfiltered)</option>
              <option value="high_volatility">High Volatility Only</option>
              <option value="low_volatility">Low Volatility Only</option>
              <option value="ranging_choppy">Ranging / Choppy Only</option>
              <option value="trending_bull">Bullish Trend Only</option>
              <option value="trending_bear">Bearish Trend Only</option>
            </select>
          </div>
        </div>

        {/* Experiment Name & Train/Test Split */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-1 border-t border-slate-800">
          <div className="md:col-span-2">
            <label className="text-[10px] text-slate-400 block mb-1">EXPERIMENT HYPOTHESIS TITLE</label>
            <input
              type="text"
              value={experimentName}
              onChange={(e) => setExperimentName(e.target.value)}
              className="w-full bg-[#080c14] border border-slate-700 rounded-xl px-3 py-1.5 text-xs text-slate-200 focus:outline-none"
            />
          </div>
          <div>
            <div className="flex justify-between text-[10px] text-slate-400 mb-1">
              <span>CHRONOLOGICAL TRAIN/TEST SPLIT</span>
              <span className="text-cyan-400 font-bold">{trainSplitPercent}% Train / {100 - trainSplitPercent}% Test</span>
            </div>
            <input
              type="range"
              min="50"
              max="85"
              step="5"
              value={trainSplitPercent}
              onChange={(e) => setTrainSplitPercent(Number(e.target.value))}
              className="w-full accent-cyan-400 cursor-pointer"
            />
          </div>
        </div>
      </div>

      {/* Experiment Results Dashboard */}
      {activeResult && (
        <div className="space-y-4 animate-in fade-in duration-300">
          {/* Scientific Verdict Banner */}
          <div
            className={`p-4 rounded-2xl border flex flex-col sm:flex-row sm:items-center justify-between gap-3 ${
              activeResult.validationVerdict === 'STATISTICALLY_SIGNIFICANT'
                ? 'bg-emerald-950/30 border-emerald-500/50 text-emerald-200'
                : activeResult.validationVerdict === 'INSUFFICIENT_EVIDENCE'
                ? 'bg-amber-950/30 border-amber-500/50 text-amber-200'
                : 'bg-rose-950/30 border-rose-500/50 text-rose-200'
            }`}
          >
            <div>
              <div className="flex items-center gap-2 mb-1">
                <span className="text-xs font-bold px-2 py-0.5 rounded-full font-mono bg-black/40 border border-current">
                  VERDICT: {activeResult.validationVerdict}
                </span>
                <span className="text-xs font-sans text-slate-300">
                  Dataset: {activeResult.config.datasetId} ({activeResult.config.symbol})
                </span>
              </div>
              <p className="text-xs font-sans leading-relaxed text-slate-200">
                {activeResult.verdictExplanation}
              </p>
            </div>

            <div className="text-right shrink-0">
              <span className="text-[10px] text-slate-400 block font-mono">P-VALUE (2-TAILED)</span>
              <span
                className={`text-xl font-bold font-mono ${
                  activeResult.outOfSample.pValue < 0.05 ? 'text-emerald-400' : 'text-amber-400'
                }`}
              >
                p = {activeResult.outOfSample.pValue}
              </span>
            </div>
          </div>

          {/* In-Sample vs Out-of-Sample Empirical Distribution Comparison */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* In-Sample Results */}
            <div className="p-4 rounded-2xl bg-[#0d121f] border border-slate-800 space-y-3">
              <div className="flex justify-between items-center border-b border-slate-800 pb-2">
                <span className="font-bold text-xs text-white">IN-SAMPLE METRICS (Train {activeResult.config.trainSplitPercent}%)</span>
                <span className="text-[10px] text-slate-400">{activeResult.inSample.sampleCount} Triggers</span>
              </div>

              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="p-2.5 bg-[#090d16] rounded-xl border border-slate-800">
                  <span className="text-[10px] text-slate-500 block">HIT RATE</span>
                  <span className="text-lg font-bold text-emerald-400">{activeResult.inSample.hitRate}%</span>
                </div>
                <div className="p-2.5 bg-[#090d16] rounded-xl border border-slate-800">
                  <span className="text-[10px] text-slate-500 block">MEAN RETURN</span>
                  <span className="text-lg font-bold text-cyan-300">{activeResult.inSample.meanReturnBps} bps</span>
                </div>
                <div className="p-2.5 bg-[#090d16] rounded-xl border border-slate-800">
                  <span className="text-[10px] text-slate-500 block">T-STATISTIC</span>
                  <span className="text-sm font-bold text-purple-300">{activeResult.inSample.tStatistic}</span>
                </div>
                <div className="p-2.5 bg-[#090d16] rounded-xl border border-slate-800">
                  <span className="text-[10px] text-slate-500 block">INFO COEFF (IC)</span>
                  <span className="text-sm font-bold text-cyan-400">{activeResult.inSample.informationCoefficient}</span>
                </div>
              </div>

              <div className="text-[10px] text-slate-400 space-y-1 pt-1">
                <div className="flex justify-between">
                  <span>Median Return:</span>
                  <span className="text-slate-200">{activeResult.inSample.medianReturnBps} bps</span>
                </div>
                <div className="flex justify-between">
                  <span>Std Deviation:</span>
                  <span className="text-slate-200">{activeResult.inSample.stdDevReturnBps} bps</span>
                </div>
                <div className="flex justify-between">
                  <span>MAE / MFE:</span>
                  <span className="text-slate-200">{activeResult.inSample.maxAdverseExcursionBps} / {activeResult.inSample.maxFavorableExcursionBps} bps</span>
                </div>
              </div>
            </div>

            {/* Out-of-Sample Results */}
            <div className="p-4 rounded-2xl bg-[#0d121f] border border-cyan-500/40 space-y-3 shadow-lg">
              <div className="flex justify-between items-center border-b border-slate-800 pb-2">
                <span className="font-bold text-xs text-cyan-300">OUT-OF-SAMPLE TEST ({100 - activeResult.config.trainSplitPercent}% Unseen)</span>
                <span className="text-[10px] text-cyan-400 font-bold">{activeResult.outOfSample.sampleCount} Triggers</span>
              </div>

              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="p-2.5 bg-[#090d16] rounded-xl border border-slate-800">
                  <span className="text-[10px] text-slate-500 block">OOS HIT RATE</span>
                  <span className={`text-lg font-bold ${activeResult.outOfSample.hitRate >= 50 ? 'text-emerald-400' : 'text-rose-400'}`}>
                    {activeResult.outOfSample.hitRate}%
                  </span>
                </div>
                <div className="p-2.5 bg-[#090d16] rounded-xl border border-slate-800">
                  <span className="text-[10px] text-slate-500 block">OOS MEAN RETURN</span>
                  <span className={`text-lg font-bold ${activeResult.outOfSample.meanReturnBps >= 0 ? 'text-cyan-300' : 'text-rose-400'}`}>
                    {activeResult.outOfSample.meanReturnBps} bps
                  </span>
                </div>
                <div className="p-2.5 bg-[#090d16] rounded-xl border border-slate-800">
                  <span className="text-[10px] text-slate-500 block">OOS T-STAT</span>
                  <span className="text-sm font-bold text-purple-300">{activeResult.outOfSample.tStatistic}</span>
                </div>
                <div className="p-2.5 bg-[#090d16] rounded-xl border border-slate-800">
                  <span className="text-[10px] text-slate-500 block">OOS INFO COEFF</span>
                  <span className="text-sm font-bold text-cyan-400">{activeResult.outOfSample.informationCoefficient}</span>
                </div>
              </div>

              <div className="text-[10px] text-slate-400 space-y-1 pt-1">
                <div className="flex justify-between">
                  <span>Median Return:</span>
                  <span className="text-slate-200">{activeResult.outOfSample.medianReturnBps} bps</span>
                </div>
                <div className="flex justify-between">
                  <span>Sharpe Ratio (Ann):</span>
                  <span className="text-emerald-400 font-bold">{activeResult.outOfSample.sharpeRatioAnnualized}</span>
                </div>
                <div className="flex justify-between">
                  <span>Quantiles (10% / 50% / 90%):</span>
                  <span className="text-slate-200">
                    {activeResult.outOfSample.returnQuantiles.q10} / {activeResult.outOfSample.returnQuantiles.q50} / {activeResult.outOfSample.returnQuantiles.q90} bps
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Baseline Benchmark Comparison Table */}
          <div className="p-4 rounded-2xl bg-[#0d121f] border border-slate-800 space-y-2">
            <span className="font-bold text-xs text-white block font-sans">
              Hypothesis Performance vs Quantitative Baselines
            </span>

            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-slate-500 border-b border-slate-800 text-left">
                    <th className="pb-2">Strategy Model</th>
                    <th className="pb-2">Hit Rate</th>
                    <th className="pb-2">Mean Return</th>
                    <th className="pb-2">Std Dev</th>
                    <th className="pb-2">t-Stat</th>
                    <th className="pb-2">p-Value</th>
                    <th className="pb-2">Sharpe</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/40">
                  <tr className="bg-cyan-950/20 text-cyan-300 font-bold">
                    <td className="py-2">Tested Hypothesis (Out-of-Sample)</td>
                    <td className="py-2">{activeResult.outOfSample.hitRate}%</td>
                    <td className="py-2">{activeResult.outOfSample.meanReturnBps} bps</td>
                    <td className="py-2">{activeResult.outOfSample.stdDevReturnBps}</td>
                    <td className="py-2">{activeResult.outOfSample.tStatistic}</td>
                    <td className="py-2">{activeResult.outOfSample.pValue}</td>
                    <td className="py-2">{activeResult.outOfSample.sharpeRatioAnnualized}</td>
                  </tr>
                  <tr className="text-slate-300">
                    <td className="py-2">Baseline 1: Zero-Signal (Unconditional)</td>
                    <td className="py-2">{activeResult.baselineZeroSignal.hitRate}%</td>
                    <td className="py-2">{activeResult.baselineZeroSignal.meanReturnBps} bps</td>
                    <td className="py-2">{activeResult.baselineZeroSignal.stdDevReturnBps}</td>
                    <td className="py-2">{activeResult.baselineZeroSignal.tStatistic}</td>
                    <td className="py-2">{activeResult.baselineZeroSignal.pValue}</td>
                    <td className="py-2">{activeResult.baselineZeroSignal.sharpeRatioAnnualized}</td>
                  </tr>
                  <tr className="text-slate-300">
                    <td className="py-2">Baseline 2: Simple Price Momentum</td>
                    <td className="py-2">{activeResult.baselineMomentum.hitRate}%</td>
                    <td className="py-2">{activeResult.baselineMomentum.meanReturnBps} bps</td>
                    <td className="py-2">{activeResult.baselineMomentum.stdDevReturnBps}</td>
                    <td className="py-2">{activeResult.baselineMomentum.tStatistic}</td>
                    <td className="py-2">{activeResult.baselineMomentum.pValue}</td>
                    <td className="py-2">{activeResult.baselineMomentum.sharpeRatioAnnualized}</td>
                  </tr>
                  <tr className="text-slate-300">
                    <td className="py-2">Baseline 3: Frozen Monthly Fisher (HL2)</td>
                    <td className="py-2">{activeResult.baselineMonthlyFisher.hitRate}%</td>
                    <td className="py-2">{activeResult.baselineMonthlyFisher.meanReturnBps} bps</td>
                    <td className="py-2">{activeResult.baselineMonthlyFisher.stdDevReturnBps}</td>
                    <td className="py-2">{activeResult.baselineMonthlyFisher.tStatistic}</td>
                    <td className="py-2">{activeResult.baselineMonthlyFisher.pValue}</td>
                    <td className="py-2">{activeResult.baselineMonthlyFisher.sharpeRatioAnnualized}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <div className="p-3 bg-[#080c14] rounded-xl border border-slate-800 text-[11px] text-slate-400 font-sans flex items-center gap-2">
            <Info className="w-4 h-4 text-cyan-400 shrink-0" />
            <span>
              <strong>Scientific Notice:</strong> Statistical correlation does not establish causality. All forward-return evaluations use chronological out-of-sample partitions without overlapping lookahead labels.
            </span>
          </div>
        </div>
      )}
    </div>
  );
};
