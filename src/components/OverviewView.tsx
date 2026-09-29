import React from 'react';
import {
  Activity,
  Layers,
  Database,
  ShieldCheck,
  CheckCircle2,
  AlertTriangle,
  FlaskConical,
  BarChart2,
  Clock,
  ArrowRight,
  TrendingUp,
  Cpu,
} from 'lucide-react';
import {
  DeltaBar,
  DataQualityReport,
  IndicatorDefinition,
  ResearchExperimentResult,
} from '../types/microstructure';
import { ResearchTabType } from './ResearchHeader';

interface OverviewViewProps {
  datasetId: string;
  symbol: string;
  bars: DeltaBar[];
  qualityReport: DataQualityReport;
  indicators: IndicatorDefinition[];
  latestExperiment: ResearchExperimentResult | null;
  onNavigateTab: (tab: ResearchTabType) => void;
}

export const OverviewView: React.FC<OverviewViewProps> = ({
  datasetId,
  symbol,
  bars,
  qualityReport,
  indicators,
  latestExperiment,
  onNavigateTab,
}) => {
  const candidateCount = indicators.filter((i) => i.status === 'RESEARCHING' || i.status === 'EXPERIMENTAL').length;
  const validatedCount = indicators.filter((i) => i.status === 'OUT_OF_SAMPLE_VALIDATED' || i.status === 'IN_SAMPLE_VALIDATED').length;
  const rejectedCount = indicators.filter((i) => i.status === 'REJECTED').length;

  const firstTimestamp = bars.length > 0 ? new Date(bars[0].timestamp).toLocaleString() : 'N/A';
  const lastTimestamp = bars.length > 0 ? new Date(bars[bars.length - 1].timestamp).toLocaleString() : 'N/A';
  const totalTrades = bars.reduce((sum, b) => sum + b.tradeCount, 0);
  const totalVolume = bars.reduce((sum, b) => sum + b.volume, 0);
  const latestClose = bars.length > 0 ? bars[bars.length - 1].close : 0;
  const latestCVD = bars.length > 0 ? bars[bars.length - 1].cumulativeVolumeDelta : 0;

  return (
    <div className="p-4 sm:p-6 space-y-5 max-w-7xl mx-auto text-slate-100">
      {/* Welcome Banner */}
      <div className="p-5 rounded-3xl bg-gradient-to-r from-[#0d1424] via-[#0b101d] to-[#11192e] border border-cyan-500/30 shadow-xl flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-mono font-bold px-2 py-0.5 rounded bg-cyan-500/20 text-cyan-300 border border-cyan-500/40">
              RESEARCH BENCHMARK
            </span>
            <span className="text-xs font-mono text-slate-400">BTCUSDT High-Resolution Microstructure</span>
          </div>
          <h1 className="text-xl sm:text-2xl font-black text-white tracking-tight">
            Delta Research & Indicator Engine V2
          </h1>
          <p className="text-xs sm:text-sm text-slate-400 max-w-2xl mt-1 leading-relaxed">
            Investigating statistical predictability of order-book depth imbalance, trade delta, and rolling-flow features for Bitcoin price discovery.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => onNavigateTab('research_lab')}
            className="px-4 py-2 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold text-xs flex items-center gap-1.5 shadow-lg shadow-cyan-500/30 transition-all"
          >
            <FlaskConical className="w-4 h-4" />
            <span>Launch Hypothesis Lab</span>
          </button>
        </div>
      </div>

      {/* 4 Metric Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 font-mono">
        {/* Dataset Coverage */}
        <div className="p-4 rounded-2xl bg-[#0d121f] border border-slate-800/80 space-y-1">
          <div className="flex items-center justify-between text-slate-400 text-xs">
            <span>DATA COVERAGE</span>
            <Database className="w-3.5 h-3.5 text-cyan-400" />
          </div>
          <div className="text-xl font-bold text-white">{bars.length} Bars</div>
          <div className="text-[11px] text-slate-400 truncate">
            {totalTrades.toLocaleString()} trades • {totalVolume.toFixed(1)} BTC
          </div>
        </div>

        {/* Data Quality Status */}
        <div className="p-4 rounded-2xl bg-[#0d121f] border border-slate-800/80 space-y-1">
          <div className="flex items-center justify-between text-slate-400 text-xs">
            <span>DATA HEALTH</span>
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
          </div>
          <div className="text-xl font-bold text-emerald-400">{qualityReport.healthScore}%</div>
          <div className="text-[11px] text-slate-400">
            {qualityReport.rejectedRecordsCount} rejected / {qualityReport.totalRecordsProcessed} events
          </div>
        </div>

        {/* Validated Indicators */}
        <div className="p-4 rounded-2xl bg-[#0d121f] border border-slate-800/80 space-y-1">
          <div className="flex items-center justify-between text-slate-400 text-xs">
            <span>VALIDATED MODELS</span>
            <CheckCircle2 className="w-3.5 h-3.5 text-purple-400" />
          </div>
          <div className="text-xl font-bold text-purple-400">{validatedCount} Validated</div>
          <div className="text-[11px] text-slate-400">
            {candidateCount} in research • {rejectedCount} rejected
          </div>
        </div>

        {/* Latest Close & CVD */}
        <div className="p-4 rounded-2xl bg-[#0d121f] border border-slate-800/80 space-y-1">
          <div className="flex items-center justify-between text-slate-400 text-xs">
            <span>LATEST BTC / CVD</span>
            <TrendingUp className="w-3.5 h-3.5 text-cyan-400" />
          </div>
          <div className="text-xl font-bold text-cyan-400">${latestClose.toLocaleString()}</div>
          <div className="text-[11px] text-slate-400">
            CVD: <span className={latestCVD >= 0 ? 'text-emerald-400' : 'text-rose-400'}>{latestCVD > 0 ? '+' : ''}{latestCVD.toFixed(2)} BTC</span>
          </div>
        </div>
      </div>

      {/* Main Multi-Pane Overview */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Left 2 Cols: Dataset Spec & Synced Microstructure Feed */}
        <div className="lg:col-span-2 space-y-4">
          {/* Active Dataset Specs Card */}
          <div className="p-4 rounded-2xl bg-[#0d121f] border border-slate-800 space-y-3">
            <div className="flex items-center justify-between border-b border-slate-800 pb-2">
              <span className="font-bold text-sm text-white flex items-center gap-2">
                <Database className="w-4 h-4 text-cyan-400" />
                Active Dataset Metadata & Time Window
              </span>
              <span className="text-xs font-mono px-2 py-0.5 rounded bg-slate-800 text-cyan-300">
                {datasetId}
              </span>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs font-mono">
              <div>
                <span className="text-slate-500 block text-[10px]">TIME RANGE START</span>
                <span className="text-slate-300">{firstTimestamp}</span>
              </div>
              <div>
                <span className="text-slate-500 block text-[10px]">TIME RANGE END</span>
                <span className="text-slate-300">{lastTimestamp}</span>
              </div>
              <div>
                <span className="text-slate-500 block text-[10px]">MEAN LATENCY DRIFT</span>
                <span className="text-slate-300">{qualityReport.meanTimestampDriftMs} ms</span>
              </div>
              <div>
                <span className="text-slate-500 block text-[10px]">SEQUENCE GAPS</span>
                <span className={qualityReport.sequenceGapCount === 0 ? 'text-emerald-400' : 'text-amber-400'}>
                  {qualityReport.sequenceGapCount} Gaps
                </span>
              </div>
            </div>
          </div>

          {/* Quick Microstructure Preview Table */}
          <div className="p-4 rounded-2xl bg-[#0d121f] border border-slate-800 space-y-2">
            <div className="flex items-center justify-between pb-2 border-b border-slate-800">
              <span className="font-bold text-xs text-white">Recent Reconstructed Delta Bars</span>
              <button
                onClick={() => onNavigateTab('delta_analytics')}
                className="text-xs text-cyan-400 hover:underline flex items-center gap-1 font-mono"
              >
                <span>Full Delta Analytics</span>
                <ArrowRight className="w-3 h-3" />
              </button>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-xs font-mono">
                <thead>
                  <tr className="text-slate-500 border-b border-slate-800 text-left">
                    <th className="pb-1.5">Time</th>
                    <th className="pb-1.5">Close Price</th>
                    <th className="pb-1.5">Volume (BTC)</th>
                    <th className="pb-1.5">Signed Delta</th>
                    <th className="pb-1.5">CVD</th>
                    <th className="pb-1.5">OB Imbalance</th>
                    <th className="pb-1.5">Regime</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/40">
                  {bars.slice(-6).reverse().map((b) => (
                    <tr key={b.timestamp} className="hover:bg-slate-800/30">
                      <td className="py-1.5 text-slate-400">{b.timeString}</td>
                      <td className="py-1.5 text-white font-bold">${b.close.toLocaleString()}</td>
                      <td className="py-1.5 text-slate-300">{b.volume.toFixed(2)}</td>
                      <td className={`py-1.5 font-bold ${b.signedDelta >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                        {b.signedDelta > 0 ? '+' : ''}{b.signedDelta.toFixed(2)}
                      </td>
                      <td className={`py-1.5 ${b.cumulativeVolumeDelta >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                        {b.cumulativeVolumeDelta.toFixed(2)}
                      </td>
                      <td className="py-1.5 text-cyan-300">
                        {b.orderBookImbalance !== 0 ? (b.orderBookImbalance * 100).toFixed(1) + '%' : '0.0%'}
                      </td>
                      <td className="py-1.5">
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-300">
                          {b.marketRegime}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* Right Col: Latest Experiment Summary & Production Status */}
        <div className="space-y-4">
          {/* Latest Experiment Status Card */}
          <div className="p-4 rounded-2xl bg-[#0d121f] border border-cyan-500/30 space-y-3">
            <div className="flex items-center justify-between border-b border-slate-800 pb-2">
              <span className="font-bold text-xs text-white flex items-center gap-1.5">
                <FlaskConical className="w-3.5 h-3.5 text-cyan-400" />
                Latest Hypothesis Run
              </span>
              {latestExperiment && (
                <span
                  className={`text-[10px] font-mono px-2 py-0.5 rounded-full font-bold ${
                    latestExperiment.validationVerdict === 'STATISTICALLY_SIGNIFICANT'
                      ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40'
                      : latestExperiment.validationVerdict === 'INSUFFICIENT_EVIDENCE'
                      ? 'bg-amber-500/20 text-amber-400 border border-amber-500/40'
                      : 'bg-rose-500/20 text-rose-400 border border-rose-500/40'
                  }`}
                >
                  {latestExperiment.validationVerdict}
                </span>
              )}
            </div>

            {latestExperiment ? (
              <div className="space-y-2 text-xs font-mono">
                <div className="text-white font-bold">{latestExperiment.config.name}</div>
                <p className="text-slate-400 font-sans text-[11px] leading-relaxed">
                  {latestExperiment.verdictExplanation}
                </p>

                <div className="grid grid-cols-2 gap-2 pt-1">
                  <div className="p-2 rounded-xl bg-[#090d16] border border-slate-800">
                    <span className="text-slate-500 text-[10px] block">OOS HIT RATE</span>
                    <span className="font-bold text-sm text-cyan-300">{latestExperiment.outOfSample.hitRate}%</span>
                  </div>
                  <div className="p-2 rounded-xl bg-[#090d16] border border-slate-800">
                    <span className="text-slate-500 text-[10px] block">P-VALUE</span>
                    <span className={`font-bold text-sm ${latestExperiment.outOfSample.pValue < 0.05 ? 'text-emerald-400' : 'text-amber-400'}`}>
                      {latestExperiment.outOfSample.pValue}
                    </span>
                  </div>
                </div>

                <button
                  onClick={() => onNavigateTab('research_lab')}
                  className="w-full py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-cyan-300 font-sans text-xs font-semibold transition-all mt-1"
                >
                  View Experiment Details
                </button>
              </div>
            ) : (
              <div className="text-center py-6 text-slate-500 text-xs">
                <p>No experiment executed yet in current session.</p>
                <button
                  onClick={() => onNavigateTab('research_lab')}
                  className="mt-2 text-cyan-400 hover:underline font-mono text-[11px]"
                >
                  + Run First Hypothesis Test
                </button>
              </div>
            )}
          </div>

          {/* Frozen Production Bridge Card */}
          <div className="p-4 rounded-2xl bg-[#0d121f] border border-purple-500/30 space-y-2.5">
            <div className="flex items-center justify-between border-b border-slate-800 pb-2">
              <span className="font-bold text-xs text-white flex items-center gap-1.5">
                <Cpu className="w-3.5 h-3.5 text-purple-400" />
                Production Status
              </span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-purple-950 text-purple-300 border border-purple-800/60">
                FROZEN PRODUCTION
              </span>
            </div>

            <div className="text-xs text-slate-300 space-y-1">
              <div className="flex justify-between font-mono">
                <span className="text-slate-500">Active Engine:</span>
                <span className="text-white font-bold">Decision Engine V1</span>
              </div>
              <div className="flex justify-between font-mono">
                <span className="text-slate-500">Production Strategy:</span>
                <span className="text-purple-300 font-bold">Monthly Fisher (HL2, len=10)</span>
              </div>
              <div className="flex justify-between font-mono">
                <span className="text-slate-500">Research Policy:</span>
                <span className="text-emerald-400">Isolated Sandbox</span>
              </div>
            </div>

            <p className="text-[11px] text-slate-400 font-sans leading-relaxed pt-1">
              Per strict quantitative risk governance, all delta-based indicators in this workstation remain in experimental quarantine until passing rigorous out-of-sample statistical criteria.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
