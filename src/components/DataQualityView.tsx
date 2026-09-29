import React from 'react';
import {
  ShieldCheck,
  AlertTriangle,
  Clock,
  Layers,
  CheckCircle2,
  XCircle,
  FileWarning,
  Activity,
} from 'lucide-react';
import { DataQualityReport } from '../types/microstructure';

interface DataQualityViewProps {
  qualityReport: DataQualityReport;
}

export const DataQualityView: React.FC<DataQualityViewProps> = ({
  qualityReport,
}) => {
  return (
    <div className="p-4 sm:p-6 space-y-5 max-w-7xl mx-auto text-slate-100 font-mono">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 p-4 rounded-2xl bg-[#0d121f] border border-slate-800">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-emerald-500/20 border border-emerald-500/40 flex items-center justify-center">
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
          </div>
          <div>
            <h2 className="font-bold text-sm text-white font-sans">
              Market Data Quality & Anomaly Audit Monitor
            </h2>
            <p className="text-[11px] text-slate-400 font-sans">
              Real-time surveillance of sequence gaps, crossed books, timestamp drift, and ingestion rejections
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <div className="px-3 py-1.5 rounded-xl bg-emerald-500/15 border border-emerald-500/30 text-emerald-400 font-bold text-xs flex items-center gap-1.5">
            <CheckCircle2 className="w-3.5 h-3.5" />
            <span>Health Score: {qualityReport.healthScore}/100</span>
          </div>
        </div>
      </div>

      {/* 5 Surveillance Counters */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 text-xs">
        <div className="p-3 bg-[#0d121f] rounded-xl border border-slate-800">
          <span className="text-slate-500 block text-[10px]">SEQUENCE GAPS</span>
          <span className={`text-lg font-bold ${qualityReport.sequenceGapCount === 0 ? 'text-emerald-400' : 'text-amber-400'}`}>
            {qualityReport.sequenceGapCount} Gaps
          </span>
        </div>
        <div className="p-3 bg-[#0d121f] rounded-xl border border-slate-800">
          <span className="text-slate-500 block text-[10px]">CROSSED BOOKS</span>
          <span className={`text-lg font-bold ${qualityReport.crossedBookCount === 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
            {qualityReport.crossedBookCount} Instances
          </span>
        </div>
        <div className="p-3 bg-[#0d121f] rounded-xl border border-slate-800">
          <span className="text-slate-500 block text-[10px]">DUPLICATE EVENTS</span>
          <span className={`text-lg font-bold ${qualityReport.duplicateEventCount === 0 ? 'text-emerald-400' : 'text-amber-400'}`}>
            {qualityReport.duplicateEventCount} Duplicates
          </span>
        </div>
        <div className="p-3 bg-[#0d121f] rounded-xl border border-slate-800">
          <span className="text-slate-500 block text-[10px]">OUT-OF-ORDER</span>
          <span className="text-lg font-bold text-slate-300">
            {qualityReport.outOfOrderCount} Events
          </span>
        </div>
        <div className="p-3 bg-[#0d121f] rounded-xl border border-slate-800">
          <span className="text-slate-500 block text-[10px]">MAX LATENCY DRIFT</span>
          <span className="text-lg font-bold text-purple-400">
            {qualityReport.maxTimestampDriftMs} ms
          </span>
        </div>
      </div>

      {/* Rejection Ledger Table */}
      <div className="p-4 rounded-2xl bg-[#0d121f] border border-slate-800 space-y-3">
        <div className="flex items-center justify-between border-b border-slate-800 pb-2">
          <span className="font-bold text-xs text-white font-sans flex items-center gap-1.5">
            <FileWarning className="w-3.5 h-3.5 text-amber-400" />
            Rejected Ingestion Records Log ({qualityReport.rejectedRecordsCount} total rejections)
          </span>
          <span className="text-xs text-slate-500">Never silently discarded per quant audit rules</span>
        </div>

        {qualityReport.rejectionLog.length === 0 ? (
          <div className="p-8 text-center text-slate-500 text-xs">
            <CheckCircle2 className="w-6 h-6 mx-auto mb-1 text-emerald-500 opacity-40" />
            <p>Pristine data quality! No records rejected in current session.</p>
          </div>
        ) : (
          <div className="overflow-x-auto max-h-72">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-slate-500 border-b border-slate-800 text-left sticky top-0 bg-[#0d121f]">
                  <th className="pb-2">Timestamp</th>
                  <th className="pb-2">Seq #</th>
                  <th className="pb-2">Rejection Reason</th>
                  <th className="pb-2">Raw Payload Sample</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/40">
                {qualityReport.rejectionLog.map((log, i) => (
                  <tr key={i} className="hover:bg-slate-800/30">
                    <td className="py-2 text-slate-400">
                      {new Date(log.timestamp).toLocaleTimeString()}
                    </td>
                    <td className="py-2 text-slate-300">{log.sequenceId}</td>
                    <td className="py-2 text-rose-400 font-bold">{log.reason}</td>
                    <td className="py-2 text-slate-500 font-mono text-[10px] truncate max-w-xs">
                      {log.rawSample}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
