import React, { useState } from 'react';
import {
  BookOpen,
  Search,
  Filter,
  Download,
  CheckCircle2,
  AlertTriangle,
  Clock,
  Layers,
  Code2,
  Trash2,
  Tag,
} from 'lucide-react';
import { IndicatorDefinition, IndicatorLifecycleStatus } from '../types/microstructure';

interface IndicatorRegistryViewProps {
  indicators: IndicatorDefinition[];
  onUpdateStatus: (id: string, status: IndicatorLifecycleStatus) => void;
  onDeleteIndicator: (id: string) => void;
}

export const IndicatorRegistryView: React.FC<IndicatorRegistryViewProps> = ({
  indicators,
  onUpdateStatus,
  onDeleteIndicator,
}) => {
  const [filterStatus, setFilterStatus] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [selectedIndicator, setSelectedIndicator] = useState<IndicatorDefinition | null>(null);

  const filtered = indicators.filter((ind) => {
    if (filterStatus !== 'all' && ind.status !== filterStatus) return false;
    if (!searchQuery) return true;
    return (
      ind.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      ind.formula.toLowerCase().includes(searchQuery.toLowerCase()) ||
      ind.id.toLowerCase().includes(searchQuery.toLowerCase())
    );
  });

  const handleExportJson = (ind: IndicatorDefinition) => {
    const jsonStr = JSON.stringify(ind, null, 2);
    const blob = new Blob([jsonStr], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `indicator-${ind.id}-v${ind.version}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const getStatusBadge = (status: IndicatorLifecycleStatus) => {
    switch (status) {
      case 'OUT_OF_SAMPLE_VALIDATED':
        return 'bg-emerald-500/20 text-emerald-400 border-emerald-500/40';
      case 'IN_SAMPLE_VALIDATED':
        return 'bg-blue-500/20 text-blue-400 border-blue-500/40';
      case 'RESEARCHING':
        return 'bg-purple-500/20 text-purple-400 border-purple-500/40';
      case 'EXPERIMENTAL':
        return 'bg-amber-500/20 text-amber-400 border-amber-500/40';
      case 'REJECTED':
        return 'bg-rose-500/20 text-rose-400 border-rose-500/40';
      case 'DRAFT':
      default:
        return 'bg-slate-800 text-slate-400 border-slate-700';
    }
  };

  return (
    <div className="p-4 sm:p-6 space-y-5 max-w-7xl mx-auto text-slate-100 font-mono">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 p-4 rounded-2xl bg-[#0d121f] border border-slate-800">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-cyan-500/20 border border-cyan-500/40 flex items-center justify-center">
            <BookOpen className="w-4 h-4 text-cyan-400" />
          </div>
          <div>
            <h2 className="font-bold text-sm text-white font-sans">
              Quantitative Indicator Registry & Governance Catalog
            </h2>
            <p className="text-[11px] text-slate-400 font-sans">
              Version-controlled repository of market microstructure indicators with empirical lifecycle tracking
            </p>
          </div>
        </div>

        <span className="text-xs font-mono px-3 py-1 rounded-xl bg-slate-800 text-cyan-300 border border-slate-700">
          {indicators.length} Registered Indicators
        </span>
      </div>

      {/* Filter and Search Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-1.5 overflow-x-auto text-xs font-sans">
          {['all', 'OUT_OF_SAMPLE_VALIDATED', 'IN_SAMPLE_VALIDATED', 'RESEARCHING', 'EXPERIMENTAL', 'DRAFT', 'REJECTED'].map((st) => (
            <button
              key={st}
              onClick={() => setFilterStatus(st)}
              className={`px-3 py-1 rounded-lg text-xs transition-all whitespace-nowrap ${
                filterStatus === st
                  ? 'bg-cyan-500 text-slate-950 font-bold'
                  : 'bg-slate-800 text-slate-400 hover:text-white'
              }`}
            >
              {st === 'all' ? 'All (8)' : st.replace(/_/g, ' ')}
            </button>
          ))}
        </div>

        <div className="relative w-full sm:w-72">
          <Search className="w-3.5 h-3.5 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            placeholder="Search indicator, formula, ID..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-[#080c14] border border-slate-800 rounded-xl pl-9 pr-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500"
          />
        </div>
      </div>

      {/* Registry Table */}
      <div className="p-4 rounded-2xl bg-[#0d121f] border border-slate-800 space-y-3">
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-slate-500 border-b border-slate-800 text-left">
                <th className="pb-2">ID & Version</th>
                <th className="pb-2">Indicator Name</th>
                <th className="pb-2">Mathematical Formula</th>
                <th className="pb-2">Timeframe</th>
                <th className="pb-2">Lifecycle Status</th>
                <th className="pb-2">Validation Metrics</th>
                <th className="pb-2 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/40">
              {filtered.map((ind) => (
                <tr key={ind.id} className="hover:bg-slate-800/30">
                  <td className="py-2.5">
                    <span className="text-slate-400">{ind.id}</span>
                    <span className="text-[10px] text-slate-500 block">v{ind.version}</span>
                  </td>
                  <td className="py-2.5 font-bold text-white font-sans">
                    {ind.name}
                    <span className="text-[11px] text-slate-400 font-sans block font-normal line-clamp-1">
                      {ind.description}
                    </span>
                  </td>
                  <td className="py-2.5 text-cyan-300 font-mono text-[11px] max-w-xs truncate">
                    <code>{ind.formula}</code>
                  </td>
                  <td className="py-2.5 text-slate-300">{ind.calculationTimeframe}</td>
                  <td className="py-2.5">
                    <select
                      value={ind.status}
                      onChange={(e) => onUpdateStatus(ind.id, e.target.value as IndicatorLifecycleStatus)}
                      className={`text-[10px] px-2 py-0.5 rounded-full border font-bold bg-[#07090e] cursor-pointer focus:outline-none ${getStatusBadge(
                        ind.status
                      )}`}
                    >
                      <option value="DRAFT">DRAFT</option>
                      <option value="RESEARCHING">RESEARCHING</option>
                      <option value="IN_SAMPLE_VALIDATED">IN_SAMPLE_VALIDATED</option>
                      <option value="OUT_OF_SAMPLE_VALIDATED">OUT_OF_SAMPLE_VALIDATED</option>
                      <option value="EXPERIMENTAL">EXPERIMENTAL</option>
                      <option value="REJECTED">REJECTED</option>
                    </select>
                  </td>
                  <td className="py-2.5 text-[11px]">
                    {ind.validationMetrics ? (
                      <div>
                        <span className="text-emerald-400 font-bold">
                          OOS Hit: {ind.validationMetrics.outOfSampleHitRate}%
                        </span>
                        <span className="text-slate-500 block text-[10px]">
                          IC: {ind.validationMetrics.outOfSampleIC} • p={ind.validationMetrics.outOfSamplePValue}
                        </span>
                      </div>
                    ) : (
                      <span className="text-slate-600">Pending Run</span>
                    )}
                  </td>
                  <td className="py-2.5 text-right space-x-1.5">
                    <button
                      onClick={() => handleExportJson(ind)}
                      className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 text-[10px]"
                      title="Export Definition JSON"
                    >
                      <Download className="w-3 h-3 inline mr-1" /> JSON
                    </button>
                    <button
                      onClick={() => onDeleteIndicator(ind.id)}
                      className="p-1 text-slate-600 hover:text-rose-400 rounded"
                      title="Delete Indicator"
                    >
                      <Trash2 className="w-3.5 h-3.5 inline" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
