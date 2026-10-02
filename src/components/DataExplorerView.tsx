import React, { useState } from 'react';
import {
  Database,
  Upload,
  Search,
  Filter,
  Download,
  AlertCircle,
  CheckCircle2,
  FileCode,
  Clock,
  Layers,
  RefreshCw,
} from 'lucide-react';
import { TradeEvent, OrderBookState, DataQualityReport } from '../types/microstructure';

interface DataExplorerViewProps {
  trades: TradeEvent[];
  orderBooks: OrderBookState[];
  rawJsonlLines: string[];
  qualityReport: DataQualityReport;
  onImportData: (rawText: string) => void;
  onResetSyntheticData: () => void;
}

export const DataExplorerView: React.FC<DataExplorerViewProps> = ({
  trades,
  orderBooks,
  rawJsonlLines,
  qualityReport,
  onImportData,
  onResetSyntheticData,
}) => {
  const [filterType, setFilterType] = useState<'all' | 'trade' | 'depth_snapshot'>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedEventRaw, setSelectedEventRaw] = useState<string | null>(null);

  // File drag-and-drop or file input
  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (event) => {
      const content = event.target?.result as string;
      if (content) {
        onImportData(content);
      }
    };
    reader.readAsText(file);
  };

  // Download current raw dataset as JSONL
  const handleExportJsonl = () => {
    const blob = new Blob([rawJsonlLines.join('\n')], { type: 'application/x-jsonlines' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `BTCUSDT-microstructure-${Date.now()}.jsonl`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="p-4 sm:p-6 space-y-5 max-w-7xl mx-auto text-slate-100 font-mono">
      {/* Header & Ingestion Toolbar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 p-4 rounded-2xl bg-[#0d121f] border border-slate-800">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-cyan-500/20 border border-cyan-500/40 flex items-center justify-center">
            <Database className="w-4 h-4 text-cyan-400" />
          </div>
          <div>
            <h2 className="font-bold text-sm text-white font-sans">Raw Market Data Ingestion & Explorer</h2>
            <p className="text-[11px] text-slate-400 font-sans">
              Research workspace uses a generated synthetic benchmark until you import exchange-captured JSONL/CSV data.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* File Upload Input */}
          <label className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-cyan-300 font-sans text-xs font-semibold cursor-pointer border border-cyan-500/30 transition-all">
            <Upload className="w-3.5 h-3.5" />
            <span>Import JSONL / CSV</span>
            <input
              type="file"
              accept=".jsonl,.json,.csv,.txt"
              onChange={handleFileUpload}
              className="hidden"
            />
          </label>

          {/* Export JSONL Button */}
          <button
            onClick={handleExportJsonl}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 font-sans text-xs font-semibold border border-slate-700 transition-all"
          >
            <Download className="w-3.5 h-3.5" />
            <span>Export JSONL</span>
          </button>

          {/* Reset to Clean Benchmark */}
          <button
            onClick={onResetSyntheticData}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white font-sans text-xs transition-all"
            title="Regenerate the synthetic 240-minute BTCUSDT research benchmark"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            <span>Reset Synthetic Benchmark</span>
          </button>
        </div>
      </div>

      {/* Ingestion Stats Row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
        <div className="p-3 bg-[#0d121f] rounded-xl border border-slate-800">
          <span className="text-slate-500 block text-[10px]">TOTAL INGESTED RECORDS</span>
          <span className="text-lg font-bold text-white">{rawJsonlLines.length.toLocaleString()}</span>
        </div>
        <div className="p-3 bg-[#0d121f] rounded-xl border border-slate-800">
          <span className="text-slate-500 block text-[10px]">VALIDATED TRADES</span>
          <span className="text-lg font-bold text-emerald-400">{trades.length.toLocaleString()}</span>
        </div>
        <div className="p-3 bg-[#0d121f] rounded-xl border border-slate-800">
          <span className="text-slate-500 block text-[10px]">BOOK SNAPSHOTS</span>
          <span className="text-lg font-bold text-cyan-400">{orderBooks.length.toLocaleString()}</span>
        </div>
        <div className="p-3 bg-[#0d121f] rounded-xl border border-slate-800">
          <span className="text-slate-500 block text-[10px]">MEAN LOCAL DRIFT</span>
          <span className="text-lg font-bold text-purple-400">{qualityReport.meanTimestampDriftMs} ms</span>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-1.5">
          <button
            onClick={() => setFilterType('all')}
            className={`px-3 py-1 rounded-lg text-xs font-sans font-medium transition-all ${
              filterType === 'all'
                ? 'bg-cyan-500 text-slate-950 font-bold'
                : 'bg-slate-800 text-slate-400 hover:text-white'
            }`}
          >
            All Events ({rawJsonlLines.length})
          </button>
          <button
            onClick={() => setFilterType('trade')}
            className={`px-3 py-1 rounded-lg text-xs font-sans font-medium transition-all ${
              filterType === 'trade'
                ? 'bg-cyan-500 text-slate-950 font-bold'
                : 'bg-slate-800 text-slate-400 hover:text-white'
            }`}
          >
            Trade Events ({trades.length})
          </button>
          <button
            onClick={() => setFilterType('depth_snapshot')}
            className={`px-3 py-1 rounded-lg text-xs font-sans font-medium transition-all ${
              filterType === 'depth_snapshot'
                ? 'bg-cyan-500 text-slate-950 font-bold'
                : 'bg-slate-800 text-slate-400 hover:text-white'
            }`}
          >
            Depth Snapshots ({orderBooks.length})
          </button>
        </div>

        <div className="relative w-full sm:w-72">
          <Search className="w-3.5 h-3.5 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            placeholder="Search price, sequence, trade ID..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-[#080c14] border border-slate-800 rounded-xl pl-9 pr-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500"
          />
        </div>
      </div>

      {/* Raw Event Stream Table */}
      <div className="p-4 rounded-2xl bg-[#0d121f] border border-slate-800 space-y-2">
        <span className="font-bold text-xs text-white block font-sans">
          Chronological Event Ledger
        </span>

        <div className="overflow-x-auto max-h-[480px]">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-slate-500 border-b border-slate-800 text-left sticky top-0 bg-[#0d121f]">
                <th className="pb-2">Seq #</th>
                <th className="pb-2">Event Type</th>
                <th className="pb-2">Exchange Time (UTC)</th>
                <th className="pb-2">Local Drift</th>
                <th className="pb-2">Side / Depth</th>
                <th className="pb-2">Execution Price</th>
                <th className="pb-2">Quantity (BTC)</th>
                <th className="pb-2 text-right">Inspect</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/40">
              {trades
                .filter((t) => {
                  if (filterType === 'depth_snapshot') return false;
                  if (!searchQuery) return true;
                  return (
                    t.tradeId.toLowerCase().includes(searchQuery.toLowerCase()) ||
                    t.price.toString().includes(searchQuery)
                  );
                })
                .slice(-100)
                .reverse()
                .map((t, idx) => {
                  const drift = Math.max(0, t.localReceiveTimestamp - t.exchangeTimestamp);
                  return (
                    <tr key={t.tradeId} className="hover:bg-slate-800/40">
                      <td className="py-1.5 text-slate-400">{t.tradeId}</td>
                      <td className="py-1.5">
                        <span className="px-1.5 py-0.2 rounded text-[10px] bg-cyan-950 text-cyan-300 border border-cyan-800/60">
                          trade
                        </span>
                      </td>
                      <td className="py-1.5 text-slate-300">
                        {new Date(t.exchangeTimestamp).toISOString().replace('T', ' ').substring(11, 23)}
                      </td>
                      <td className="py-1.5 text-slate-400">+{drift}ms</td>
                      <td className="py-1.5">
                        <span
                          className={`font-bold ${
                            t.side === 'buy' ? 'text-emerald-400' : 'text-rose-400'
                          }`}
                        >
                          {t.side.toUpperCase()}
                        </span>
                      </td>
                      <td className="py-1.5 text-white font-bold">${t.price.toFixed(2)}</td>
                      <td className="py-1.5 text-slate-300">{t.size.toFixed(4)}</td>
                      <td className="py-1.5 text-right">
                        <button
                          onClick={() => setSelectedEventRaw(JSON.stringify(t, null, 2))}
                          className="px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-cyan-300 text-[10px]"
                        >
                          JSON
                        </button>
                      </td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Raw Event Inspector Modal */}
      {selectedEventRaw && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="w-full max-w-lg bg-[#0d121f] border border-cyan-500/50 rounded-2xl shadow-2xl p-4 space-y-3">
            <div className="flex items-center justify-between border-b border-slate-800 pb-2">
              <span className="font-bold text-xs text-white flex items-center gap-2">
                <FileCode className="w-4 h-4 text-cyan-400" />
                Raw Event Inspector
              </span>
              <button
                onClick={() => setSelectedEventRaw(null)}
                className="text-xs text-slate-400 hover:text-white"
              >
                Close
              </button>
            </div>
            <pre className="p-3 bg-[#07090e] border border-slate-800 rounded-xl text-[11px] text-cyan-300 overflow-x-auto max-h-96">
              {selectedEventRaw}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
};
