import React, { useState } from 'react';
import {
  Settings,
  Shield,
  Play,
  CheckCircle2,
  XCircle,
  Download,
  Database,
  Cpu,
  RefreshCw,
  FileSpreadsheet,
} from 'lucide-react';
import { FROZEN_MONTHLY_FISHER, DeltaBar, IndicatorDefinition } from '../types/microstructure';
import { runMicrostructureTestSuite, TestResultItem } from '../utils/microstructureTests';

interface SettingsAndBridgeViewProps {
  bars: DeltaBar[];
  indicators: IndicatorDefinition[];
}

export const SettingsAndBridgeView: React.FC<SettingsAndBridgeViewProps> = ({
  bars,
  indicators,
}) => {
  const [testResults, setTestResults] = useState<TestResultItem[]>([]);
  const [isRunningTests, setIsRunningTests] = useState(false);

  const handleExecuteTests = () => {
    setIsRunningTests(true);
    setTimeout(() => {
      const results = runMicrostructureTestSuite();
      setTestResults(results);
      setIsRunningTests(false);
    }, 200);
  };

  const handleExportFeaturesCsv = () => {
    if (bars.length === 0) return;
    const headers = [
      'timestamp',
      'timeString',
      'open',
      'high',
      'low',
      'close',
      'volume',
      'buyVolume',
      'sellVolume',
      'signedDelta',
      'cumulativeVolumeDelta',
      'tradeCount',
      'buyTradeCount',
      'sellTradeCount',
      'tradeCountImbalance',
      'orderBookImbalance',
      'rollingDeltaAcceleration',
      'priceImpactPerVolume',
      'flowPersistence',
      'marketRegime',
    ];

    const rows = bars.map((b) => [
      b.timestamp,
      `"${b.timeString}"`,
      b.open,
      b.high,
      b.low,
      b.close,
      b.volume,
      b.buyVolume,
      b.sellVolume,
      b.signedDelta,
      b.cumulativeVolumeDelta,
      b.tradeCount,
      b.buyTradeCount,
      b.sellTradeCount,
      b.tradeCountImbalance,
      b.orderBookImbalance,
      b.rollingDeltaAcceleration,
      b.priceImpactPerVolume,
      b.flowPersistence,
      `"${b.marketRegime}"`,
    ]);

    const csvContent = [headers.join(','), ...rows.map((r) => r.join(','))].join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `BTCUSDT-features-${Date.now()}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleExportIndicatorsJson = () => {
    const jsonStr = JSON.stringify(indicators, null, 2);
    const blob = new Blob([jsonStr], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `delta-indicators-registry-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="p-4 sm:p-6 space-y-5 max-w-7xl mx-auto text-slate-100 font-mono">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 p-4 rounded-2xl bg-[#0d121f] border border-slate-800">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-purple-500/20 border border-purple-500/40 flex items-center justify-center">
            <Settings className="w-4 h-4 text-purple-400" />
          </div>
          <div>
            <h2 className="font-bold text-sm text-white font-sans">
              Settings, Production Governance & Test Suite
            </h2>
            <p className="text-[11px] text-slate-400 font-sans">
              Inspect frozen production Monthly Fisher specifications, export feature matrices, and execute automated unit tests
            </p>
          </div>
        </div>

        <button
          onClick={handleExecuteTests}
          disabled={isRunningTests}
          className="flex items-center gap-2 px-4 py-2 rounded-xl bg-purple-600 hover:bg-purple-500 text-white font-bold font-sans text-xs shadow-lg shadow-purple-600/25 transition-all disabled:opacity-50"
        >
          <Play className={`w-3.5 h-3.5 fill-current ${isRunningTests ? 'animate-spin' : ''}`} />
          <span>{isRunningTests ? 'Running Assertions...' : 'Run Quantitative Test Suite'}</span>
        </button>
      </div>

      {/* Frozen Production Strategy Card */}
      <div className="p-5 rounded-2xl bg-[#0d121f] border border-purple-500/40 space-y-3">
        <div className="flex items-center justify-between border-b border-slate-800 pb-2">
          <div className="flex items-center gap-2">
            <Shield className="w-4 h-4 text-purple-400" />
            <span className="font-bold text-sm text-white">Frozen Production Strategy: Monthly Fisher</span>
          </div>
          <span className="text-[10px] px-2 py-0.5 rounded font-bold bg-purple-950 text-purple-300 border border-purple-800/60">
            FROZEN / COMPLIANT
          </span>
        </div>

        <p className="text-xs text-slate-300 font-sans leading-relaxed">
          The production Monthly Fisher algorithm executes on Decision Engine V1. Per project mandate, this baseline logic is immutable and frozen. Research indicators operate in parallel without altering live execution parameters.
        </p>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs pt-1">
          <div className="p-3 bg-[#090d16] rounded-xl border border-slate-800">
            <span className="text-slate-500 block text-[10px]">SOURCE PRICE</span>
            <span className="font-bold text-cyan-300">{FROZEN_MONTHLY_FISHER.source} ((High + Low) / 2)</span>
          </div>
          <div className="p-3 bg-[#090d16] rounded-xl border border-slate-800">
            <span className="text-slate-500 block text-[10px]">LENGTH</span>
            <span className="font-bold text-white">{FROZEN_MONTHLY_FISHER.length} Periods</span>
          </div>
          <div className="p-3 bg-[#090d16] rounded-xl border border-slate-800">
            <span className="text-slate-500 block text-[10px]">ALPHA COEFF</span>
            <span className="font-bold text-white">{FROZEN_MONTHLY_FISHER.alpha}</span>
          </div>
          <div className="p-3 bg-[#090d16] rounded-xl border border-slate-800">
            <span className="text-slate-500 block text-[10px]">BETA COEFF</span>
            <span className="font-bold text-white">{FROZEN_MONTHLY_FISHER.beta}</span>
          </div>
        </div>
      </div>

      {/* Automated Microstructure Unit Test Suite */}
      <div className="p-5 rounded-2xl bg-[#0d121f] border border-slate-800 space-y-3">
        <div className="flex items-center justify-between border-b border-slate-800 pb-2">
          <span className="font-bold text-xs text-white font-sans">
            Automated Mathematical Verification Test Suite ({testResults.length} Tests)
          </span>
          <span className="text-xs text-slate-500">
            Tests Delta Math, Crossed Books, Sequence Audits, and No-Lookahead Invariants
          </span>
        </div>

        {testResults.length === 0 ? (
          <div className="text-center py-6 text-slate-500 text-xs">
            <p>Click "Run Quantitative Test Suite" above to verify all mathematical formulas and safeguards.</p>
          </div>
        ) : (
          <div className="space-y-1.5">
            {testResults.map((t, idx) => (
              <div
                key={idx}
                className="p-2.5 rounded-xl bg-[#090d16] border border-slate-800 flex items-center justify-between text-xs"
              >
                <div className="flex items-center gap-2.5">
                  {t.passed ? (
                    <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                  ) : (
                    <XCircle className="w-4 h-4 text-rose-400 shrink-0" />
                  )}
                  <div>
                    <span className="font-bold text-white">{t.name}</span>
                    <span className="text-slate-500 ml-2 text-[10px]">[{t.category}]</span>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <span className={`text-[11px] ${t.passed ? 'text-emerald-400' : 'text-rose-400'}`}>
                    {t.message}
                  </span>
                  <span className="text-slate-500 text-[10px]">{t.durationMs}ms</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Export Options */}
      <div className="p-5 rounded-2xl bg-[#0d121f] border border-slate-800 space-y-3">
        <span className="font-bold text-xs text-white block font-sans">
          Quantitative Dataset & Catalog Export Options
        </span>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
          <button
            onClick={handleExportFeaturesCsv}
            className="p-3 bg-[#090d16] hover:bg-slate-800/80 rounded-xl border border-slate-800 flex items-center justify-between text-left transition-all"
          >
            <div>
              <span className="font-bold text-white block font-sans">Export Feature Matrix (CSV)</span>
              <span className="text-[11px] text-slate-400 font-sans">
                Exports all {bars.length} bars with signed delta, CVD, imbalance, and regimes.
              </span>
            </div>
            <FileSpreadsheet className="w-5 h-5 text-emerald-400 shrink-0 ml-2" />
          </button>

          <button
            onClick={handleExportIndicatorsJson}
            className="p-3 bg-[#090d16] hover:bg-slate-800/80 rounded-xl border border-slate-800 flex items-center justify-between text-left transition-all"
          >
            <div>
              <span className="font-bold text-white block font-sans">Export Indicator Catalog (JSON)</span>
              <span className="text-[11px] text-slate-400 font-sans">
                Exports all {indicators.length} registered indicator specifications and formulas.
              </span>
            </div>
            <Download className="w-5 h-5 text-cyan-400 shrink-0 ml-2" />
          </button>
        </div>
      </div>
    </div>
  );
};
