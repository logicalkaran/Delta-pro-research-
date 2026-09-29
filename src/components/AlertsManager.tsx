import React, { useState } from 'react';
import {
  Bell,
  Plus,
  Trash2,
  Volume2,
  VolumeX,
  CheckCircle2,
  Clock,
  Zap,
  Sparkles,
  Play,
} from 'lucide-react';
import { AlertRule, AlertCondition, AlertNotification, Ticker } from '../types/crypto';

interface AlertsManagerProps {
  alertRules: AlertRule[];
  onAddAlertRule: (rule: Omit<AlertRule, 'id' | 'createdAt'>) => void;
  onDeleteAlertRule: (id: string) => void;
  onToggleAlertRule: (id: string) => void;
  triggeredHistory: AlertNotification[];
  onClearHistory: () => void;
  onTestTriggerAlert: () => void;
  tickers: Ticker[];
  currentSymbol: string;
}

export const AlertsManager: React.FC<AlertsManagerProps> = ({
  alertRules,
  onAddAlertRule,
  onDeleteAlertRule,
  onToggleAlertRule,
  triggeredHistory,
  onClearHistory,
  onTestTriggerAlert,
  tickers,
  currentSymbol,
}) => {
  const [isCreating, setIsCreating] = useState(false);
  const [symbol, setSymbol] = useState(currentSymbol || 'BTCUSD');
  const [condition, setCondition] = useState<AlertCondition>('crosses_above');
  const [targetValue, setTargetValue] = useState<string>('95000');
  const [note, setNote] = useState<string>('Target price reached on Delta Exchange');
  const [soundEnabled, setSoundEnabled] = useState(true);

  // Set default target price based on selected symbol
  const handleSymbolChange = (sym: string) => {
    setSymbol(sym);
    const found = tickers.find((t) => t.symbol === sym);
    if (found) {
      if (condition === 'crosses_above') {
        setTargetValue((found.mark_price * 1.02).toFixed(2));
      } else if (condition === 'crosses_below') {
        setTargetValue((found.mark_price * 0.98).toFixed(2));
      }
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const val = parseFloat(targetValue);
    if (isNaN(val)) return;

    onAddAlertRule({
      symbol,
      condition,
      targetValue: val,
      note: note || `Alert when ${symbol} ${condition} ${val}`,
      soundEnabled,
      active: true,
    });

    setIsCreating(false);
  };

  const getConditionLabel = (cond: AlertCondition, val: number) => {
    switch (cond) {
      case 'crosses_above':
        return `Crosses Above $${val.toLocaleString()}`;
      case 'crosses_below':
        return `Crosses Below $${val.toLocaleString()}`;
      case 'change_percent_above':
        return `24h Change > +${val}%`;
      case 'change_percent_below':
        return `24h Change < -${val}%`;
      case 'rsi_overbought':
        return `RSI Overbought (> ${val || 70})`;
      case 'rsi_oversold':
        return `RSI Oversold (< ${val || 30})`;
      case 'funding_rate_above':
        return `8h Funding Rate > ${(val * 100).toFixed(3)}%`;
      default:
        return `${cond} ${val}`;
    }
  };

  return (
    <div className="flex flex-col h-full bg-[#080c14] select-none text-slate-100 p-3 overflow-y-auto space-y-4">
      {/* Header Bar */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-xl bg-amber-500/20 border border-amber-500/40 flex items-center justify-center">
            <Bell className="w-4 h-4 text-amber-400" />
          </div>
          <div>
            <h2 className="font-bold text-sm text-white">Automated Price Alerts</h2>
            <p className="text-[11px] text-slate-400">
              Live background monitoring with audio push notification
            </p>
          </div>
        </div>

        <div className="flex items-center gap-1.5">
          <button
            onClick={onTestTriggerAlert}
            className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-cyan-300 text-xs font-mono font-medium border border-cyan-500/30 transition-all"
            title="Simulate instant alert with audio chime"
          >
            <Play className="w-3 h-3 fill-cyan-400 text-cyan-400" />
            <span>Test Sound</span>
          </button>

          <button
            onClick={() => setIsCreating(true)}
            className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-slate-950 text-xs font-bold shadow-md shadow-cyan-500/30 transition-all"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>New Alert</span>
          </button>
        </div>
      </div>

      {/* Alert Creator Modal / Accordion */}
      {isCreating && (
        <form
          onSubmit={handleSubmit}
          className="p-3.5 bg-[#0f1523] border border-cyan-500/40 rounded-2xl shadow-xl space-y-3 animate-in fade-in duration-200"
        >
          <div className="flex items-center justify-between border-b border-slate-800 pb-2">
            <span className="font-bold text-xs text-white flex items-center gap-1.5">
              <Zap className="w-3.5 h-3.5 text-cyan-400" />
              Configure Alert Rule
            </span>
            <button
              type="button"
              onClick={() => setIsCreating(false)}
              className="text-xs text-slate-400 hover:text-white"
            >
              Cancel
            </button>
          </div>

          <div className="grid grid-cols-2 gap-2 text-xs">
            {/* Symbol Selection */}
            <div>
              <label className="text-[10px] text-slate-400 font-mono block mb-1">Target Asset</label>
              <select
                value={symbol}
                onChange={(e) => handleSymbolChange(e.target.value)}
                className="w-full bg-[#080c14] border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-white focus:outline-none focus:border-cyan-500 font-mono"
              >
                {tickers.map((t) => (
                  <option key={t.symbol} value={t.symbol}>
                    {t.symbol} (${t.mark_price.toLocaleString()})
                  </option>
                ))}
              </select>
            </div>

            {/* Condition Selection */}
            <div>
              <label className="text-[10px] text-slate-400 font-mono block mb-1">Condition</label>
              <select
                value={condition}
                onChange={(e) => setCondition(e.target.value as AlertCondition)}
                className="w-full bg-[#080c14] border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-white focus:outline-none focus:border-cyan-500 font-mono"
              >
                <option value="crosses_above">Price Crosses Above</option>
                <option value="crosses_below">Price Crosses Below</option>
                <option value="change_percent_above">24h Gain exceeds %</option>
                <option value="change_percent_below">24h Drop exceeds %</option>
                <option value="rsi_overbought">RSI Overbought (&gt; 70)</option>
                <option value="rsi_oversold">RSI Oversold (&lt; 30)</option>
                <option value="funding_rate_above">Funding Rate Spike (&gt; 0.03%)</option>
              </select>
            </div>
          </div>

          {/* Target Value Input */}
          <div>
            <label className="text-[10px] text-slate-400 font-mono block mb-1">
              Target Value (USD or %)
            </label>
            <input
              type="number"
              step="any"
              required
              value={targetValue}
              onChange={(e) => setTargetValue(e.target.value)}
              placeholder="e.g. 95000"
              className="w-full bg-[#080c14] border border-slate-700 rounded-lg px-3 py-1.5 text-xs font-mono text-white focus:outline-none focus:border-cyan-500"
            />
          </div>

          {/* Alert Note */}
          <div>
            <label className="text-[10px] text-slate-400 font-mono block mb-1">Custom Note</label>
            <input
              type="text"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="e.g. BTC breakout above resistance, look for long entry"
              className="w-full bg-[#080c14] border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white focus:outline-none focus:border-cyan-500"
            />
          </div>

          {/* Sound Toggle */}
          <div className="flex items-center justify-between pt-1">
            <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
              <input
                type="checkbox"
                checked={soundEnabled}
                onChange={(e) => setSoundEnabled(e.target.checked)}
                className="rounded border-slate-700 text-cyan-500 focus:ring-0"
              />
              <span className="flex items-center gap-1 font-mono text-[11px]">
                <Volume2 className="w-3.5 h-3.5 text-cyan-400" />
                Play Android Audio Bell
              </span>
            </label>

            <button
              type="submit"
              className="px-4 py-1.5 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-slate-950 text-xs font-bold shadow-md shadow-cyan-500/30"
            >
              Activate Alert
            </button>
          </div>
        </form>
      )}

      {/* Active Alert Rules Section */}
      <div className="space-y-2">
        <div className="flex items-center justify-between text-xs text-slate-400 font-mono">
          <span>ACTIVE RULES ({alertRules.filter((r) => r.active).length})</span>
          <span className="text-[10px]">Real-time tick engine</span>
        </div>

        {alertRules.length === 0 ? (
          <div className="p-6 bg-[#0c101a] border border-slate-800/80 rounded-2xl text-center text-slate-500 text-xs">
            <Bell className="w-6 h-6 mx-auto mb-2 opacity-30" />
            <p>No active price alerts set.</p>
            <button
              onClick={() => setIsCreating(true)}
              className="mt-2 text-cyan-400 hover:underline font-mono text-[11px]"
            >
              + Create your first alert
            </button>
          </div>
        ) : (
          <div className="space-y-2">
            {alertRules.map((rule) => (
              <div
                key={rule.id}
                className={`p-3 rounded-xl border transition-all ${
                  rule.active
                    ? 'bg-[#0e1422] border-slate-800 hover:border-slate-700'
                    : 'bg-[#090d16] border-slate-900 opacity-60'
                }`}
              >
                <div className="flex items-start justify-between">
                  <div className="flex items-start gap-2.5">
                    <button
                      onClick={() => onToggleAlertRule(rule.id)}
                      className={`p-1.5 rounded-lg mt-0.5 transition-colors ${
                        rule.active
                          ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/40'
                          : 'bg-slate-800 text-slate-500'
                      }`}
                      title={rule.active ? 'Disable alert' : 'Enable alert'}
                    >
                      <Bell className="w-3.5 h-3.5" />
                    </button>

                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-xs text-white font-mono">{rule.symbol}</span>
                        <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-slate-800 text-cyan-300">
                          {getConditionLabel(rule.condition, rule.targetValue)}
                        </span>
                      </div>
                      <p className="text-[11px] text-slate-300 mt-1">{rule.note}</p>
                    </div>
                  </div>

                  <div className="flex items-center gap-1.5">
                    {rule.soundEnabled ? (
                      <span title="Audio chime active">
                        <Volume2 className="w-3.5 h-3.5 text-slate-400" />
                      </span>
                    ) : (
                      <span title="Muted">
                        <VolumeX className="w-3.5 h-3.5 text-slate-600" />
                      </span>
                    )}
                    <button
                      onClick={() => onDeleteAlertRule(rule.id)}
                      className="p-1 text-slate-500 hover:text-rose-400 rounded transition-colors"
                      title="Delete alert"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Triggered Alert Notifications History */}
      <div className="space-y-2 pt-2 border-t border-slate-800/80">
        <div className="flex items-center justify-between text-xs text-slate-400 font-mono">
          <div className="flex items-center gap-1.5">
            <Clock className="w-3.5 h-3.5 text-amber-400" />
            <span>TRIGGERED HISTORY ({triggeredHistory.length})</span>
          </div>
          {triggeredHistory.length > 0 && (
            <button
              onClick={onClearHistory}
              className="text-[10px] text-slate-500 hover:text-slate-300 transition-colors"
            >
              Clear Log
            </button>
          )}
        </div>

        {triggeredHistory.length === 0 ? (
          <div className="p-4 bg-[#0c101a] border border-slate-800/60 rounded-xl text-center text-slate-500 text-xs">
            <CheckCircle2 className="w-5 h-5 mx-auto mb-1 opacity-30 text-emerald-500" />
            <p>No alerts have triggered yet.</p>
          </div>
        ) : (
          <div className="space-y-1.5 max-h-[220px] overflow-y-auto">
            {triggeredHistory.map((item) => (
              <div
                key={item.id}
                className="p-2.5 bg-[#0e1320] border border-amber-500/20 rounded-xl flex items-start justify-between text-xs font-mono"
              >
                <div>
                  <div className="flex items-center gap-1.5">
                    <span className="font-bold text-white">{item.symbol}</span>
                    <span className="text-[10px] text-amber-400 font-semibold">{item.title}</span>
                  </div>
                  <p className="text-[11px] text-slate-300 font-sans mt-0.5">{item.message}</p>
                </div>
                <div className="text-right text-[10px] text-slate-400">
                  <div className="text-cyan-400 font-bold">${item.price.toLocaleString()}</div>
                  <span>{new Date(item.timestamp).toLocaleTimeString()}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
