import React, { useState } from 'react';
import {
  Wrench,
  Plus,
  Code2,
  Check,
  Sparkles,
  Sliders,
  Shield,
  Layers,
  ArrowRight,
  Database,
} from 'lucide-react';
import { IndicatorDefinition, IndicatorLifecycleStatus } from '../types/microstructure';

interface IndicatorBuilderViewProps {
  onRegisterIndicator: (indicator: IndicatorDefinition) => void;
}

export const IndicatorBuilderView: React.FC<IndicatorBuilderViewProps> = ({
  onRegisterIndicator,
}) => {
  const [name, setName] = useState('Adaptive Order-Flow Squeeze');
  const [version, setVersion] = useState('1.0.0');
  const [formula, setFormula] = useState('AOFS = (SignedDelta / TotalVolume) * (1 + NOBI_10)');
  const [description, setDescription] = useState(
    'Combines volume-normalized aggressive delta with passive L10 book skew for breakout identification.'
  );
  const [rollingWindow, setRollingWindow] = useState<number>(14);
  const [threshold, setThreshold] = useState<number>(0.2);
  const [smoothing, setSmoothing] = useState<'SMA' | 'EMA' | 'None'>('EMA');
  const [normalization, setNormalization] = useState<'ZScore' | 'MinMax' | 'None'>('ZScore');
  const [missingDataBehavior, setMissingDataBehavior] = useState<'drop_and_warn' | 'hold_last' | 'interpolate'>('drop_and_warn');
  const [warmupPeriod, setWarmupPeriod] = useState<number>(20);
  const [longSignal, setLongSignal] = useState('AOFS > 0.20 && PriceImpact > 1.5');
  const [shortSignal, setShortSignal] = useState('AOFS < -0.20 && PriceImpact > 1.5');
  const [exitSignal, setExitSignal] = useState('abs(AOFS) < 0.05 || cross(AOFS, 0)');
  const [savedSuccess, setSavedSuccess] = useState(false);

  const handleRegister = (e: React.FormEvent) => {
    e.preventDefault();

    const newInd: IndicatorDefinition = {
      id: `ind-${Date.now()}`,
      name,
      version,
      formula,
      description,
      requiredFields: ['signedDelta', 'volume', 'depthImbalance10'],
      parameters: {
        rollingWindow,
        threshold,
        smoothing,
        normalization,
      },
      calculationTimeframe: '1m',
      warmupPeriod,
      signalDefinition: {
        longCondition: longSignal,
        shortCondition: shortSignal,
        exitCondition: exitSignal,
      },
      missingDataBehavior,
      status: 'DRAFT', // Per quantitative guidelines: always starts as DRAFT or RESEARCHING, never automatically validated!
      createdAt: Date.now(),
    };

    onRegisterIndicator(newInd);
    setSavedSuccess(true);
    setTimeout(() => setSavedSuccess(false), 3000);
  };

  return (
    <div className="p-4 sm:p-6 space-y-5 max-w-7xl mx-auto text-slate-100 font-mono">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 p-4 rounded-2xl bg-[#0d121f] border border-slate-800">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-cyan-500/20 border border-cyan-500/40 flex items-center justify-center">
            <Wrench className="w-4 h-4 text-cyan-400" />
          </div>
          <div>
            <h2 className="font-bold text-sm text-white font-sans">
              Indicator Development Workbench
            </h2>
            <p className="text-[11px] text-slate-400 font-sans">
              Author and parameterize research indicator definitions with strict mathematical specifications
            </p>
          </div>
        </div>

        {savedSuccess && (
          <div className="px-3 py-1.5 rounded-xl bg-emerald-500/20 border border-emerald-500/40 text-emerald-300 text-xs font-sans flex items-center gap-1.5 animate-in fade-in">
            <Check className="w-4 h-4" />
            <span>Indicator Registered as DRAFT in Registry!</span>
          </div>
        )}
      </div>

      <form onSubmit={handleRegister} className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Left 2 Cols: Form Parameters */}
        <div className="lg:col-span-2 p-5 rounded-2xl bg-[#0d121f] border border-slate-800 space-y-4 text-xs">
          <span className="font-bold text-sm text-white block font-sans">
            Indicator Specification
          </span>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="sm:col-span-2">
              <label className="text-[10px] text-slate-400 block mb-1">INDICATOR NAME</label>
              <input
                type="text"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full bg-[#080c14] border border-slate-700 rounded-xl px-3 py-1.5 text-xs text-white focus:outline-none focus:border-cyan-500 font-mono"
              />
            </div>
            <div>
              <label className="text-[10px] text-slate-400 block mb-1">VERSION</label>
              <input
                type="text"
                required
                value={version}
                onChange={(e) => setVersion(e.target.value)}
                className="w-full bg-[#080c14] border border-slate-700 rounded-xl px-3 py-1.5 text-xs text-cyan-300 focus:outline-none font-mono"
              />
            </div>
          </div>

          <div>
            <label className="text-[10px] text-slate-400 block mb-1">MATHEMATICAL FORMULA</label>
            <input
              type="text"
              required
              value={formula}
              onChange={(e) => setFormula(e.target.value)}
              className="w-full bg-[#080c14] border border-slate-700 rounded-xl px-3 py-2 text-xs text-cyan-400 font-mono focus:outline-none focus:border-cyan-500"
            />
          </div>

          <div>
            <label className="text-[10px] text-slate-400 block mb-1">RESEARCH HYPOTHESIS & DESCRIPTION</label>
            <textarea
              rows={2}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="w-full bg-[#080c14] border border-slate-700 rounded-xl p-2.5 text-xs text-slate-200 focus:outline-none font-sans"
            />
          </div>

          {/* Parameters Grid */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2 border-t border-slate-800">
            <div>
              <label className="text-[10px] text-slate-400 block mb-1">ROLLING WINDOW</label>
              <input
                type="number"
                value={rollingWindow}
                onChange={(e) => setRollingWindow(Number(e.target.value))}
                className="w-full bg-[#080c14] border border-slate-700 rounded-xl px-2.5 py-1.5 text-xs text-white"
              />
            </div>
            <div>
              <label className="text-[10px] text-slate-400 block mb-1">THRESHOLD</label>
              <input
                type="number"
                step="0.05"
                value={threshold}
                onChange={(e) => setThreshold(Number(e.target.value))}
                className="w-full bg-[#080c14] border border-slate-700 rounded-xl px-2.5 py-1.5 text-xs text-white"
              />
            </div>
            <div>
              <label className="text-[10px] text-slate-400 block mb-1">SMOOTHING</label>
              <select
                value={smoothing}
                onChange={(e) => setSmoothing(e.target.value as any)}
                className="w-full bg-[#080c14] border border-slate-700 rounded-xl px-2 py-1.5 text-xs text-white"
              >
                <option value="EMA">EMA</option>
                <option value="SMA">SMA</option>
                <option value="None">None (Raw)</option>
              </select>
            </div>
            <div>
              <label className="text-[10px] text-slate-400 block mb-1">NORMALIZATION</label>
              <select
                value={normalization}
                onChange={(e) => setNormalization(e.target.value as any)}
                className="w-full bg-[#080c14] border border-slate-700 rounded-xl px-2 py-1.5 text-xs text-white"
              >
                <option value="ZScore">Z-Score</option>
                <option value="MinMax">Min-Max [-1, 1]</option>
                <option value="None">None</option>
              </select>
            </div>
          </div>

          {/* Signal Rules */}
          <div className="space-y-2 pt-2 border-t border-slate-800">
            <span className="text-[10px] text-slate-400 block font-bold">SIGNAL RULES & MISSING DATA POLICY</span>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
              <div>
                <label className="text-[9px] text-emerald-400 block mb-0.5">LONG CONDITION</label>
                <input
                  type="text"
                  value={longSignal}
                  onChange={(e) => setLongSignal(e.target.value)}
                  className="w-full bg-[#080c14] border border-slate-700 rounded-lg p-1.5 text-[11px] text-slate-200"
                />
              </div>
              <div>
                <label className="text-[9px] text-rose-400 block mb-0.5">SHORT CONDITION</label>
                <input
                  type="text"
                  value={shortSignal}
                  onChange={(e) => setShortSignal(e.target.value)}
                  className="w-full bg-[#080c14] border border-slate-700 rounded-lg p-1.5 text-[11px] text-slate-200"
                />
              </div>
              <div>
                <label className="text-[9px] text-cyan-400 block mb-0.5">EXIT CONDITION</label>
                <input
                  type="text"
                  value={exitSignal}
                  onChange={(e) => setExitSignal(e.target.value)}
                  className="w-full bg-[#080c14] border border-slate-700 rounded-lg p-1.5 text-[11px] text-slate-200"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3 pt-2">
              <div>
                <label className="text-[10px] text-slate-400 block mb-1">WARM-UP BARS REQUIREMENT</label>
                <input
                  type="number"
                  value={warmupPeriod}
                  onChange={(e) => setWarmupPeriod(Number(e.target.value))}
                  className="w-full bg-[#080c14] border border-slate-700 rounded-xl px-2.5 py-1.5 text-xs text-white"
                />
              </div>
              <div>
                <label className="text-[10px] text-slate-400 block mb-1">MISSING DATA BEHAVIOR</label>
                <select
                  value={missingDataBehavior}
                  onChange={(e) => setMissingDataBehavior(e.target.value as any)}
                  className="w-full bg-[#080c14] border border-slate-700 rounded-xl px-2.5 py-1.5 text-xs text-white"
                >
                  <option value="drop_and_warn">Drop & Flag Warning (Safest)</option>
                  <option value="hold_last">Hold Last Known Value</option>
                  <option value="interpolate">Linear Interpolation</option>
                </select>
              </div>
            </div>
          </div>

          <button
            type="submit"
            className="w-full py-2.5 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold font-sans text-xs flex items-center justify-center gap-2 shadow-lg shadow-cyan-500/25 transition-all"
          >
            <Plus className="w-4 h-4" />
            <span>Register Indicator into Quantitative Catalog</span>
          </button>
        </div>

        {/* Right Col: Mathematical Preview & Lifecycle Policy */}
        <div className="p-5 rounded-2xl bg-[#0d121f] border border-slate-800 space-y-4 text-xs font-sans">
          <span className="font-bold text-sm text-white block">
            Research Lifecycle Protocol
          </span>

          <div className="p-3 bg-[#080c14] rounded-xl border border-slate-800 space-y-2 text-[11px] text-slate-300">
            <span className="text-cyan-400 font-bold font-mono block">Status Progression:</span>
            <div className="space-y-1 font-mono text-[10px]">
              <div className="text-slate-400">1. DRAFT (Authoring)</div>
              <div className="text-purple-300">2. RESEARCHING (Hypothesis Testing)</div>
              <div className="text-blue-300">3. IN_SAMPLE_VALIDATED (p &lt; 0.05 Train)</div>
              <div className="text-emerald-400 font-bold">4. OUT_OF_SAMPLE_VALIDATED (Holdout Test)</div>
              <div className="text-rose-400">5. REJECTED (Overfit / Insufficient IC)</div>
            </div>
          </div>

          <div className="space-y-2 text-slate-400 text-xs">
            <span className="text-white font-bold block text-xs">Compliance Rules:</span>
            <p className="leading-relaxed">
              • Newly created indicators are assigned <code>DRAFT</code> status by default.
            </p>
            <p className="leading-relaxed">
              • An indicator may ONLY be promoted to <code>OUT_OF_SAMPLE_VALIDATED</code> after passing a chronological holdout test with sample size N &ge; 30, p &lt; 0.05, and positive Information Coefficient (IC).
            </p>
            <p className="leading-relaxed">
              • Research indicators are strictly isolated from production Decision Engine V1.
            </p>
          </div>
        </div>
      </form>
    </div>
  );
};
