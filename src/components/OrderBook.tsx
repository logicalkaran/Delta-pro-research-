import React, { useEffect, useMemo, useState } from 'react';

interface Level { price: number; size: number; total: number }
interface Trade { id: string; price: number; size: number; side: 'buy' | 'sell' | 'unknown'; timestamp: number }
interface BookResponse { success: boolean; source: string; symbol: string; fetchedAt: number; exchangeTimestamp: number | null; bids: Level[]; asks: Level[] }
interface TradesResponse { success: boolean; source: string; symbol: string; fetchedAt: number; trades: Trade[] }

interface OrderBookProps { markPrice: number; symbol: string; bestBid: number; bestAsk: number }

export const OrderBook: React.FC<OrderBookProps> = ({ markPrice, symbol, bestBid, bestAsk }) => {
  const [activeTab, setActiveTab] = useState<'depth' | 'trades'>('depth');
  const [book, setBook] = useState<BookResponse | null>(null);
  const [trades, setTrades] = useState<TradesResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const [bookRes, tradesRes] = await Promise.all([
          fetch(`/api/delta/orderbook/${encodeURIComponent(symbol)}`),
          fetch(`/api/delta/trades/${encodeURIComponent(symbol)}`),
        ]);
        const [bookData, tradesData] = await Promise.all([bookRes.json(), tradesRes.json()]);
        if (!bookRes.ok || !bookData.success) throw new Error(bookData.error || 'Order book unavailable');
        if (!tradesRes.ok || !tradesData.success) throw new Error(tradesData.error || 'Trades unavailable');
        if (alive) {
          setBook(bookData);
          setTrades(tradesData);
          setError(null);
        }
      } catch (e) {
        if (alive) {
          setBook(null);
          setTrades(null);
          setError(e instanceof Error ? e.message : 'Market feed unavailable');
        }
      }
    };
    load();
    const interval = setInterval(load, 2500);
    return () => { alive = false; clearInterval(interval); };
  }, [symbol]);

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  const spread = bestBid > 0 && bestAsk > 0 ? Math.max(0, bestAsk - bestBid) : 0;
  const spreadPercent = markPrice > 0 ? (spread / markPrice) * 100 : 0;
  const maxDepth = Math.max(1, ...(book?.bids || []).map(x => x.total), ...(book?.asks || []).map(x => x.total));
  const freshness = useMemo(() => {
    const timestamp = book?.exchangeTimestamp ?? trades?.trades?.[0]?.timestamp ?? null;
    return timestamp ? Math.max(0, Math.floor((now - timestamp) / 1000)) : null;
  }, [book, trades, now]);

  return (
    <div className="bg-[#0b0f19] border-t border-slate-800/80 p-2 text-xs font-mono select-none">
      <div className="flex items-center justify-between gap-2 pb-1.5 border-b border-slate-800/60 mb-2">
        <div className="flex items-center gap-2">
          <button onClick={() => setActiveTab('depth')} className={`px-2 py-0.5 rounded text-[11px] font-semibold ${activeTab === 'depth' ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/40' : 'text-slate-400'}`}>Order Book</button>
          <button onClick={() => setActiveTab('trades')} className={`px-2 py-0.5 rounded text-[11px] font-semibold ${activeTab === 'trades' ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/40' : 'text-slate-400'}`}>Recent Trades</button>
        </div>
        <div className="text-[10px] text-slate-400 text-right">
          <span className={error ? 'text-rose-400' : freshness !== null && freshness > 15 ? 'text-amber-400' : 'text-emerald-400'}>
            {error ? 'FEED UNAVAILABLE' : freshness !== null && freshness > 15 ? 'STALE SNAPSHOT' : 'DELTA REST'}
          </span>
          <span className="ml-2">{freshness === null ? 'Timestamp n/a' : `Exchange age ${freshness}s`}</span>
        </div>
      </div>
      {error ? <div className="py-8 text-center text-rose-300">{error}. No simulated market data is displayed.</div> : activeTab === 'depth' ? (
        <div>
          <div className="grid grid-cols-3 text-[10px] text-slate-500 pb-1 px-1"><span>Price (USD)</span><span className="text-right">Size</span><span className="text-right">Cumulative</span></div>
          {book?.asks.slice(0, 8).reverse().map((a, i) => <div key={`ask-${a.price}-${i}`} className="grid grid-cols-3 py-0.5 px-1 relative text-[11px]">
            <div className="absolute inset-y-0 right-0 bg-rose-500/10 pointer-events-none" style={{ width: `${Math.min(100, a.total / maxDepth * 100)}%` }} />
            <span className="text-rose-400 z-10">{a.price.toFixed(2)}</span><span className="text-right text-slate-300 z-10">{a.size.toLocaleString()}</span><span className="text-right text-slate-400 z-10">{a.total.toLocaleString()}</span>
          </div>)}
          <div className="my-1.5 py-1 px-2 bg-slate-900/90 rounded border border-slate-800 flex items-center justify-between">
            <span className="text-sm font-bold text-cyan-400">{markPrice > 0 ? markPrice.toFixed(2) : '—'}</span>
            <span className="text-[10px] text-slate-400">Spread {spread > 0 ? `${spread.toFixed(2)} (${spreadPercent.toFixed(3)}%)` : '—'}</span>
          </div>
          {book?.bids.slice(0, 8).map((b, i) => <div key={`bid-${b.price}-${i}`} className="grid grid-cols-3 py-0.5 px-1 relative text-[11px]">
            <div className="absolute inset-y-0 right-0 bg-emerald-500/10 pointer-events-none" style={{ width: `${Math.min(100, b.total / maxDepth * 100)}%` }} />
            <span className="text-emerald-400 z-10">{b.price.toFixed(2)}</span><span className="text-right text-slate-300 z-10">{b.size.toLocaleString()}</span><span className="text-right text-slate-400 z-10">{b.total.toLocaleString()}</span>
          </div>)}
          {!book && <div className="py-5 text-center text-slate-500">Waiting for exchange order book…</div>}
          {book && <div className="pt-2 text-[10px] text-slate-500">Source: Delta Exchange India public L2 snapshot · fetched {new Date(book.fetchedAt).toLocaleTimeString()}</div>}
        </div>
      ) : (
        <div className="space-y-1 max-h-[190px] overflow-y-auto">
          <div className="grid grid-cols-3 text-[10px] text-slate-500 pb-1 px-1"><span>Price (USD)</span><span className="text-right">Size</span><span className="text-right">Exchange time</span></div>
          {trades?.trades.map(t => <div key={t.id} className="grid grid-cols-3 py-0.5 px-1 text-[11px] border-b border-slate-800/30">
            <span className={t.side === 'buy' ? 'text-emerald-400' : t.side === 'sell' ? 'text-rose-400' : 'text-slate-300'}>{t.price.toFixed(2)}</span>
            <span className="text-right text-slate-300">{t.size.toLocaleString()}</span>
            <span className="text-right text-slate-400">{new Date(t.timestamp).toLocaleTimeString()}</span>
          </div>)}
          {trades?.trades.length === 0 && <div className="py-5 text-center text-slate-500">No recent trades returned by exchange.</div>}
          {!trades && <div className="py-5 text-center text-slate-500">Waiting for exchange trades…</div>}
          {trades && <div className="pt-2 text-[10px] text-slate-500">Source: Delta Exchange India public trades · fetched {new Date(trades.fetchedAt).toLocaleTimeString()}</div>}
        </div>
      )}
    </div>
  );
};
