import React, { useEffect, useMemo, useState } from 'react';
import { Candle } from '../types/crypto';
import { atr, dmi, ema, macd, relativeVolume, realizedVolatility, rsi, validateCandleSeries, vwap } from '../utils/advancedIndicators';
import { calculateBollingerBands } from '../utils/indicators';
import { runWalkForwardResearch, WalkForwardResult, ResearchStrategy } from '../utils/researchBacktest';

interface Props { candles: Candle[]; symbol: string; resolution: string; }

const fmt = (v: number | null | undefined, digits = 2) => v == null || !Number.isFinite(v) ? 'Warm-up / n.a.' : v.toFixed(digits);
type SavedBacktestRun = { id: string; strategy: ResearchStrategy; feeBps: number; slippageBps: number; candleCount: number; startTime: number; endTime: number; oosReturnPct: number; oosTrades: number; worstDrawdownPct: number; };

export const IndicatorWorkbenchView: React.FC<Props> = ({ candles, symbol, resolution }) => {
  const [replayCandles, setReplayCandles] = useState<Candle[]>(candles);
  const [datasetName, setDatasetName] = useState('Exchange candles currently loaded');
  const [index, setIndex] = useState(Math.max(0, candles.length - 1));
  const [strategy, setStrategy] = useState<ResearchStrategy>('ema_cross');
  const [feeBps, setFeeBps] = useState(5);
  const [slippageBps, setSlippageBps] = useState(3);
  const [backtest, setBacktest] = useState<WalkForwardResult | null>(null);
  const [backtestHistory, setBacktestHistory] = useState<SavedBacktestRun[]>(() => {
    try { return JSON.parse(localStorage.getItem('deltapro_walkforward_runs') || '[]'); } catch { return []; }
  });
  useEffect(() => { try { localStorage.setItem('deltapro_walkforward_runs', JSON.stringify(backtestHistory.slice(0, 10))); } catch {} }, [backtestHistory]);
  const runBacktest = () => {
    const result = runWalkForwardResearch(replayCandles, { strategy, feeBps, slippageBps }, 4);
    setBacktest(result);
    if (replayCandles.length) setBacktestHistory(prev => [{
      id: `${Date.now()}-${replayCandles.length}`, strategy, feeBps, slippageBps,
      candleCount: replayCandles.length, startTime: replayCandles[0].time,
      endTime: replayCandles[replayCandles.length - 1].time,
      oosReturnPct: result.compoundedOosReturnPct, oosTrades: result.totalOosTrades,
      worstDrawdownPct: result.worstFoldDrawdownPct,
    }, ...prev].slice(0, 10));
  };
  useEffect(() => { setReplayCandles(candles); setDatasetName('Exchange candles currently loaded'); setIndex(Math.max(0, candles.length - 1)); setBacktest(null); }, [candles]);
  const safeIndex = Math.min(index, Math.max(0, replayCandles.length - 1));
  const series = useMemo(() => {
    const closes = replayCandles.map(c => c.close);
    return { ema20: ema(closes, 20), ema50: ema(closes, 50), bb: calculateBollingerBands(closes, 20, 2), rsi: rsi(closes), atr: atr(replayCandles), dmi: dmi(replayCandles), macd: macd(closes), vwap: vwap(replayCandles), rv: realizedVolatility(replayCandles), relVol: relativeVolume(replayCandles) };
  }, [replayCandles]);
  const quality = useMemo(() => validateCandleSeries(replayCandles), [replayCandles]);
  const c = replayCandles[safeIndex];
  const rows = [
    ['EMA (20)', series.ema20[safeIndex], 'Exponential moving average, 20 closes', 'Trend reference; lagging, not a standalone signal'],
    ['EMA (50)', series.ema50[safeIndex], 'Exponential moving average, 50 closes', 'Trend reference; lagging, not a standalone signal'],
    ['Bollinger upper', series.bb.upper[safeIndex], 'SMA20 + 2 population standard deviations', 'Band width changes with recent price dispersion'],
    ['Bollinger middle', series.bb.middle[safeIndex], 'SMA20', 'Rolling centerline'],
    ['Bollinger lower', series.bb.lower[safeIndex], 'SMA20 − 2 population standard deviations', 'Bands are not guaranteed support/resistance'],
    ['RSI (14)', series.rsi[safeIndex], 'Momentum; Wilder smoothing', '70/30 are common reference levels, not trade instructions'],
    ['ATR (14)', series.atr[safeIndex], 'True-range volatility, Wilder smoothing', 'Absolute price units; not direction'],
    ['+DI (14)', series.dmi.plusDI[safeIndex], 'Wilder-smoothed positive directional movement / TR', 'Directional movement component'],
    ['−DI (14)', series.dmi.minusDI[safeIndex], 'Wilder-smoothed negative directional movement / TR', 'Directional movement component'],
    ['ADX (14)', series.dmi.adx[safeIndex], 'Wilder-smoothed directional index', 'Trend strength, not direction; compare +DI and −DI'], 
    ['MACD (12,26,9)', series.macd.macd[safeIndex], 'EMA12 − EMA26', 'Signal/histogram below'],
    ['MACD signal', series.macd.signal[safeIndex], 'EMA9 of MACD', 'Warm-up values are intentionally null'],
    ['MACD histogram', series.macd.histogram[safeIndex], 'MACD − signal', 'Zero-centered momentum measure'],
    ['Cumulative VWAP', series.vwap[safeIndex], 'Cumulative typical-price × volume / volume', 'Anchored to first candle currently loaded'],
    ['Realized volatility', series.rv[safeIndex], 'Rolling log-return standard deviation × √period', 'Percent-like scaled measure; period-normalized'],
    ['Relative volume', series.relVol[safeIndex], 'Current volume / prior 20-bar mean', 'Uses prior bars only; no look-ahead'],
  ] as const;
  const exportCsv = () => {
    const header = ['time','open','high','low','close','volume','ema20','ema50','bbUpper20','bbMiddle20','bbLower20','rsi14','atr14','plusDI14','minusDI14','adx14','macd','macdSignal','macdHistogram','vwapLoadedWindow','realizedVol20','relativeVolume20'];
    const body = replayCandles.map((bar, i) => [bar.time,bar.open,bar.high,bar.low,bar.close,bar.volume,series.ema20[i],series.ema50[i],series.bb.upper[i],series.bb.middle[i],series.bb.lower[i],series.rsi[i],series.atr[i],series.dmi.plusDI[i],series.dmi.minusDI[i],series.dmi.adx[i],series.macd.macd[i],series.macd.signal[i],series.macd.histogram[i],series.vwap[i],series.rv[i],series.relVol[i]].map(v => v == null ? '' : String(v)).join(','));
    const blob = new Blob([[header.join(','), ...body].join('\n')], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = `${symbol}-${resolution}-indicator-research.csv`; a.click(); URL.revokeObjectURL(url);
  };
  const importCandles = (file: File) => {
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const lines = String(reader.result || '').split(String.fromCharCode(10)).filter(line => line.trim());
        if (lines.length < 2) throw new Error('CSV must include a header and candle rows.');
        const headers = lines[0].replace(String.fromCharCode(65279), '').split(',').map(x => x.trim().toLowerCase());
        const find = (...keys: string[]) => headers.findIndex(h => keys.includes(h));
        const ti = find('time','timestamp','date','datetime');
        const oi = find('open'), hi = find('high'), li = find('low'), ci = find('close'), vi = find('volume','vol');
        if ([ti,oi,hi,li,ci,vi].some(i => i < 0)) throw new Error('Required CSV columns: time/timestamp, open, high, low, close, volume.');
        const parsed: Candle[] = lines.slice(1).map(line => {
          const cells = line.split(',');
          const rawTime = (cells[ti] || '').trim(), numericTime = Number(rawTime);
          const time = rawTime && Number.isFinite(numericTime) ? (numericTime < 1e12 ? numericTime * 1000 : numericTime) : Date.parse(rawTime);
          return { time, open: Number(cells[oi]), high: Number(cells[hi]), low: Number(cells[li]), close: Number(cells[ci]), volume: Number(cells[vi]) };
        }).filter(row => [row.time,row.open,row.high,row.low,row.close,row.volume].every(Number.isFinite));
        if (!parsed.length) throw new Error('No valid candle rows found. Check timestamps and numeric OHLCV fields.');
        setReplayCandles(parsed); setIndex(parsed.length - 1); setDatasetName(`Imported CSV: ${file.name}`); setBacktest(null);
        window.alert(`Imported ${parsed.length} candle rows. Review data-quality diagnostics before research.`);
      } catch (error) { window.alert(error instanceof Error ? error.message : 'Could not parse candle CSV.'); }
    };
    reader.readAsText(file);
  };
  return <section className="p-4 sm:p-6 max-w-7xl mx-auto space-y-4 text-slate-100 font-mono">
    <div className="rounded-2xl border border-slate-800 bg-[#0d121f] p-4 flex flex-wrap items-center justify-between gap-3">
      <div><h2 className="font-bold text-white font-sans">Indicator Workbench & Historical Replay</h2><p className="text-xs text-slate-400 mt-1">Read-only indicator diagnostics. Source: {datasetName}. No order execution or signal promotion.</p></div>
      <div className="flex gap-2"><label className="px-3 py-2 rounded-lg bg-slate-800 text-cyan-200 text-xs font-semibold cursor-pointer">Import candle CSV<input type="file" accept=".csv,text/csv" className="hidden" onChange={e=>{const file=e.target.files?.[0]; if(file) importCandles(file); e.currentTarget.value='';}} /></label><button onClick={exportCsv} disabled={!replayCandles.length} className="px-3 py-2 rounded-lg bg-cyan-500 text-slate-950 text-xs font-bold disabled:opacity-40">Export indicator CSV</button></div>
    </div>
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
      {[
        ['Candles', quality.rows], ['Invalid OHLC', quality.invalidOHLC], ['Invalid values', quality.invalidValues], ['Duplicate timestamps', quality.duplicateTimes],
        ['Non-monotonic', quality.nonMonotonic], ['Detected gaps', quality.detectedGaps], ['Median interval', quality.medianIntervalMs ? `${Math.round(quality.medianIntervalMs/1000)}s` : 'n/a'], ['Loaded range', replayCandles.length ? new Date(replayCandles[0].time).toLocaleString() : 'No data']
      ].map(([label,value]) => <div key={String(label)} className="rounded-xl bg-[#0d121f] border border-slate-800 p-3"><div className="text-[10px] text-slate-500">{label}</div><div className="font-bold text-white mt-1">{value}</div></div>)}
    </div>
    <div className="rounded-2xl border border-slate-800 bg-[#0d121f] p-4 space-y-3">
      <div className="flex justify-between text-xs"><span className="text-slate-300">Replay candle</span><span className="text-cyan-300">{c ? new Date(c.time).toLocaleString() : 'No candles'}</span></div>
      <input aria-label="Historical replay candle" type="range" min="0" max={Math.max(0,replayCandles.length-1)} value={safeIndex} onChange={e=>setIndex(Number(e.target.value))} disabled={!replayCandles.length} className="w-full accent-cyan-400"/>
      <div className="flex justify-between text-[10px] text-slate-500"><span>First loaded candle</span><span>{safeIndex+1} / {replayCandles.length}</span><span>Latest loaded candle</span></div>
      {c && <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 text-xs">{[['Open',c.open],['High',c.high],['Low',c.low],['Close',c.close],['Volume',c.volume]].map(([k,v])=><div key={String(k)} className="bg-slate-900 rounded-lg p-2"><div className="text-[10px] text-slate-500">{k}</div><div className="text-white">{Number(v).toLocaleString(undefined,{maximumFractionDigits:4})}</div></div>)}</div>}
    </div>
    <div className="rounded-2xl border border-slate-800 bg-[#0d121f] p-4 space-y-3">
      <div><h3 className="text-sm font-bold text-white">Cost-aware walk-forward OOS research (fixed rules)</h3><p className="text-[11px] text-slate-400 mt-1">Signals use completed candles and execute at the next candle open. One unleveraged unit; fee and slippage are charged on entry and exit. Research only.</p></div>
      <div className="grid grid-cols-1 sm:grid-cols-4 gap-2 text-xs">
        <label className="text-slate-400">Strategy<select value={strategy} onChange={e=>setStrategy(e.target.value as ResearchStrategy)} className="block mt-1 w-full rounded-lg bg-slate-900 border border-slate-700 p-2 text-white"><option value="ema_cross">EMA 12/26 crossover</option><option value="rsi_reversal">RSI 14 threshold reversal</option><option value="range_breakout">20-bar range breakout</option></select></label>
        <label className="text-slate-400">Fee (bps / side)<input type="number" min="0" step="0.1" value={feeBps} onChange={e=>setFeeBps(Math.max(0,Number(e.target.value)||0))} className="block mt-1 w-full rounded-lg bg-slate-900 border border-slate-700 p-2 text-white" /></label>
        <label className="text-slate-400">Slippage (bps / side)<input type="number" min="0" step="0.1" value={slippageBps} onChange={e=>setSlippageBps(Math.max(0,Number(e.target.value)||0))} className="block mt-1 w-full rounded-lg bg-slate-900 border border-slate-700 p-2 text-white" /></label>
        <button onClick={runBacktest} disabled={replayCandles.length < 40} className="self-end rounded-lg bg-cyan-500 p-2 font-bold text-slate-950 disabled:opacity-40">Run walk-forward</button>
      </div>
      {backtest && <div className="space-y-3"><div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">{[['Full sample return',`${backtest.fullSample.totalReturnPct.toFixed(2)}%`],['Full sample trades',backtest.fullSample.trades.length],['Compounded OOS return',`${backtest.compoundedOosReturnPct.toFixed(2)}%`],['OOS trades',backtest.totalOosTrades],['Worst fold drawdown',`${backtest.worstFoldDrawdownPct.toFixed(2)}%`],['Fee + slippage each side',`${(feeBps+slippageBps).toFixed(2)} bps`]].map(([k,v])=><div key={String(k)} className="rounded-lg bg-slate-900 p-3"><div className="text-[10px] text-slate-500">{k}</div><div className="text-white font-bold mt-1">{v}</div></div>)}</div><div className="overflow-x-auto"><table className="w-full text-[11px]"><thead><tr className="text-slate-500 text-left"><th className="py-2">OOS fold</th><th>Range</th><th>Trades</th><th>Net return</th><th>Win rate</th><th>Profit factor</th><th>Max DD</th></tr></thead><tbody>{backtest.folds.map((f,i)=><tr key={i} className="border-t border-slate-800 text-slate-300"><td className="py-2">{i+1}</td><td>{replayCandles[f.startIndex] ? new Date(replayCandles[f.startIndex].time).toLocaleDateString() : '—'} – {replayCandles[f.endIndex] ? new Date(replayCandles[f.endIndex].time).toLocaleDateString() : '—'}</td><td>{f.trades.length}</td><td>{f.totalReturnPct.toFixed(2)}%</td><td>{f.winRatePct.toFixed(1)}%</td><td>{Number.isFinite(f.profitFactor) ? f.profitFactor.toFixed(2) : '∞'}</td><td>{f.maxDrawdownPct.toFixed(2)}%</td></tr>)}</tbody></table></div><p className="text-[10px] text-amber-300">These are exploratory results on the currently loaded candle window. No funding, liquidation, market impact beyond the configured slippage, or partial fills are modeled. Out-of-sample folds start flat; parameters are fixed (not optimized on the training half). This is research, not a live strategy recommendation.</p></div>}
    </div>
    <div className="rounded-2xl border border-slate-800 bg-[#0d121f] overflow-hidden">
      <div className="p-3 border-b border-slate-800 font-bold text-xs">Indicator values at replay cursor · {symbol} · {resolution}</div>
      <div className="divide-y divide-slate-800">{rows.map(([name,value,formula,note])=><div key={name} className="p-3 grid grid-cols-1 sm:grid-cols-[1fr_130px_2fr] gap-1 sm:gap-3 text-xs"><div className="text-white font-semibold">{name}<div className="text-[10px] text-slate-500 font-normal mt-1">{formula}</div></div><div className="text-cyan-300 font-bold">{fmt(value)}</div><div className="text-slate-400">{note}</div></div>)}</div>
    </div>
    <div className="rounded-xl border border-slate-800 bg-[#0d121f] p-3 space-y-2">
      <div className="flex justify-between"><h3 className="text-xs font-bold text-white">Saved walk-forward runs · this device</h3><span className="text-[10px] text-slate-500">{backtestHistory.length}/10</span></div>
      {backtestHistory.length ? backtestHistory.map(run => <div key={run.id} className="border-t border-slate-800 pt-2 text-[11px] text-slate-300 flex flex-wrap justify-between gap-2"><span>{run.strategy} · {run.candleCount} bars · {new Date(run.startTime).toLocaleDateString()}–{new Date(run.endTime).toLocaleDateString()}</span><span>OOS {run.oosReturnPct.toFixed(2)}% · N={run.oosTrades} · DD {run.worstDrawdownPct.toFixed(2)}% · costs {run.feeBps+run.slippageBps} bps/side</span></div>) : <p className="text-[11px] text-slate-500">Run a backtest to store its configuration and summary locally.</p>}
      <button onClick={() => { if (window.confirm('Clear saved walk-forward run summaries from this device?')) setBacktestHistory([]); }} disabled={!backtestHistory.length} className="text-[10px] text-rose-300 disabled:opacity-40">Clear saved runs</button>
    </div>
    <p className="text-[11px] text-amber-300">Research caution: indicator outputs are descriptive calculations, not validated predictive edges. Replay uses the selected exchange candles or an imported CSV. Exchange response length is limited; verify timestamp coverage and quality before research. VWAP restarts at the first loaded candle.</p>
  </section>;
};
