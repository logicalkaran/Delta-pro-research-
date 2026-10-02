import React from 'react';
import {
  Activity,
  Layers,
  BarChart3,
  FlaskConical,
  Wrench,
  FileCheck2,
  BookOpen,
  ShieldCheck,
  Settings,
  Download,
  Database,
  Radio,
  Maximize2,
  ChevronDown,
  Sparkles,
} from 'lucide-react';

export type ResearchTabType =
  | 'overview'
  | 'data_explorer'
  | 'order_book'
  | 'delta_analytics'
  | 'research_lab'
  | 'indicator_workbench'
  | 'indicator_builder'
  | 'validation_reports'
  | 'indicator_registry'
  | 'data_quality'
  | 'settings_bridge';

interface ResearchHeaderProps {
  activeTab: ResearchTabType;
  setActiveTab: (tab: ResearchTabType) => void;
  datasetId: string;
  setDatasetId: (id: string) => void;
  healthScore: number;
  totalRecords: number;
  onOpenDownloadModal: () => void;
  symbol: string;
  isLive: boolean;
}

export const ResearchHeader: React.FC<ResearchHeaderProps> = ({
  activeTab,
  setActiveTab,
  datasetId,
  setDatasetId,
  healthScore,
  totalRecords,
  onOpenDownloadModal,
  symbol,
  isLive,
}) => {
  const navTabs: { id: ResearchTabType; label: string; icon: React.ReactNode }[] = [
    { id: 'overview', label: '1. Overview', icon: <Activity className="w-3.5 h-3.5" /> },
    { id: 'data_explorer', label: '2. Data Explorer', icon: <Database className="w-3.5 h-3.5" /> },
    { id: 'order_book', label: '3. Order Book', icon: <Layers className="w-3.5 h-3.5" /> },
    { id: 'delta_analytics', label: '4. Delta Analytics', icon: <BarChart3 className="w-3.5 h-3.5" /> },
    { id: 'research_lab', label: '5. Research Lab', icon: <FlaskConical className="w-3.5 h-3.5" /> },
    { id: 'indicator_workbench', label: '6. Indicator Workbench', icon: <BarChart3 className="w-3.5 h-3.5" /> },
    { id: 'indicator_builder', label: '7. Indicator Builder', icon: <Wrench className="w-3.5 h-3.5" /> },
    { id: 'validation_reports', label: '8. Validation Reports', icon: <FileCheck2 className="w-3.5 h-3.5" /> },
    { id: 'indicator_registry', label: '9. Indicator Registry', icon: <BookOpen className="w-3.5 h-3.5" /> },
    { id: 'data_quality', label: '10. Data Quality', icon: <ShieldCheck className="w-3.5 h-3.5" /> },
    { id: 'settings_bridge', label: '11. Settings & Baseline', icon: <Settings className="w-3.5 h-3.5" /> },
  ];

  return (
    <header className="bg-[#0a0e1a] border-b border-slate-800/90 text-slate-200 select-none shrink-0 sticky top-0 z-40">
      {/* Top Bar: Brand, Dataset Identifier, Quality Status */}
      <div className="px-3 sm:px-5 py-2.5 flex flex-wrap items-center justify-between gap-3 border-b border-slate-800/60">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-xl bg-gradient-to-tr from-cyan-600 via-blue-600 to-indigo-600 flex items-center justify-center shadow-lg shadow-cyan-500/20">
            <span className="font-extrabold text-white text-base tracking-tighter">Δ</span>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-bold text-sm tracking-wide text-white">DELTA RESEARCH ENGINE</span>
              <span className="text-[10px] px-2 py-0.5 rounded font-mono font-bold bg-cyan-950 text-cyan-300 border border-cyan-800/60">
                V2.4 QUANT
              </span>
              <span className="flex items-center gap-1.5 text-[10px] font-mono px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                {isLive ? 'EXCHANGE L2 FEED' : 'HISTORICAL REPLAY'}
              </span>
            </div>
            <p className="text-[11px] text-slate-400 hidden sm:block">
              Market Microstructure, Order-Flow Delta & Empirical Hypothesis Validation
            </p>
          </div>
        </div>

        {/* Dataset, Symbol & Quality Indicator */}
        <div className="flex items-center gap-2 font-mono text-xs">
          {/* Symbol Tag */}
          <div className="px-2.5 py-1 rounded-xl bg-slate-900 border border-slate-800 flex items-center gap-1.5">
            <span className="text-slate-500 text-[10px]">ASSET:</span>
            <span className="font-bold text-white text-xs">{symbol}</span>
          </div>

          {/* Dataset Selector */}
          <div className="relative">
            <select
              value={datasetId}
              onChange={(e) => setDatasetId(e.target.value)}
              className="bg-slate-900 border border-slate-800 text-cyan-300 rounded-xl px-2.5 py-1 text-xs font-mono focus:outline-none focus:border-cyan-500 cursor-pointer pr-7"
            >
              <option value="BTCUSDT-L2-SYNTH-240M">BTCUSDT-L2-SYNTH-240M (Benchmark)</option>
              <option value="BTCUSDT-HIGH-VOLATILITY">BTCUSDT-HIGH-VOLATILITY-DATASET</option>
              <option value="BTCUSDT-RANGE-ABSORPTION">BTCUSDT-RANGE-ABSORPTION-FEED</option>
              <option value="CUSTOM-IMPORTED-JSONL">CUSTOM-IMPORTED-JSONL</option>
            </select>
            <ChevronDown className="w-3.5 h-3.5 text-slate-400 absolute right-2 top-1/2 -translate-y-1/2 pointer-events-none" />
          </div>

          {/* Data Quality Health Score Badge */}
          <div
            className={`px-2.5 py-1 rounded-xl border flex items-center gap-1.5 ${
              healthScore >= 95
                ? 'bg-emerald-500/15 border-emerald-500/40 text-emerald-400'
                : healthScore >= 80
                ? 'bg-amber-500/15 border-amber-500/40 text-amber-400'
                : 'bg-rose-500/15 border-rose-500/40 text-rose-400'
            }`}
            title={`${totalRecords.toLocaleString()} records processed. Health Score: ${healthScore}/100`}
          >
            <ShieldCheck className="w-3.5 h-3.5" />
            <span className="font-bold">{healthScore}% HEALTH</span>
          </div>

          {/* Download App Button */}
          <button
            onClick={onOpenDownloadModal}
            className="flex items-center gap-1.5 px-3 py-1 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold font-sans text-xs transition-all shadow-md shadow-cyan-500/20"
          >
            <Download className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Export / Install</span>
          </button>
        </div>
      </div>

      {/* Primary 10 Navigation Tabs */}
      <nav className="flex items-center gap-1 px-3 py-1.5 overflow-x-auto text-xs no-scrollbar bg-[#070a12]">
        {navTabs.map((tab) => {
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg whitespace-nowrap font-medium text-xs transition-all ${
                isActive
                  ? 'bg-cyan-500/20 text-cyan-300 font-bold border border-cyan-500/40 shadow-sm'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60 border border-transparent'
              }`}
            >
              {tab.icon}
              <span>{tab.label}</span>
            </button>
          );
        })}
      </nav>
    </header>
  );
};
