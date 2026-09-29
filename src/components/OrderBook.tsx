import React, { useState, useEffect } from 'react';
import { TradeTick } from '../types/crypto';

interface OrderBookProps {
  markPrice: number;
  symbol: string;
  bestBid: number;
  bestAsk: number;
  onQuickTrade?: (side: 'LONG' | 'SHORT', price: number) => void;
}

export const OrderBook: React.FC<OrderBookProps> = ({
  markPrice,
  symbol,
  bestBid,
  bestAsk,
  onQuickTrade,
}) => {
  const [activeTab, setActiveTab] = useState<'depth' | 'trades'>('depth');
  const [recentTrades, setRecentTrades] = useState<TradeTick[]>([]);

  // Calculate dynamic ladder around mark price
  const spread = Math.max(0.1, bestAsk - bestBid);
  const spreadPercent = markPrice > 0 ? (spread / markPrice) * 100 : 0.01;

  // Generate 7 levels of bids and 7 levels of asks
  const step = markPrice > 50000 ? 5 : markPrice > 1000 ? 0.5 : 0.05;

  const asks = [];
  let totalAskSize = 0;
  for (let i = 6; i >= 0; i--) {
    const p = Number((bestAsk + (i + 1) * step).toFixed(2));
    const size = Number((Math.random() * 2.5 + 0.4).toFixed(3));
    totalAskSize += size;
    asks.push({ price: p, size, total: totalAskSize });
  }

  const bids = [];
  let totalBidSize = 0;
  for (let i = 0; i < 7; i++) {
    const p = Number((bestBid - (i + 1) * step).toFixed(2));
    const size = Number((Math.random() * 2.8 + 0.5).toFixed(3));
    totalBidSize += size;
    bids.push({ price: p, size, total: totalBidSize });
  }

  const maxTotal = Math.max(totalAskSize, totalBidSize);

  // Generate continuous live micro trades
  useEffect(() => {
    const initialTrades: TradeTick[] = [];
    const now = Date.now();
    for (let i = 10; i >= 0; i--) {
      const isBuy = Math.random() > 0.48;
      const tPrice = isBuy
        ? bestAsk + (Math.random() * 2 - 1)
        : bestBid + (Math.random() * 2 - 1);
      initialTrades.push({
        id: `trade-${now - i * 1500}`,
        price: Number(tPrice.toFixed(2)),
        size: Number((Math.random() * 1.8 + 0.1).toFixed(3)),
        side: isBuy ? 'buy' : 'sell',
        time: new Date(now - i * 1500).toLocaleTimeString([], {
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
        }),
      });
    }
    setRecentTrades(initialTrades);

    const interval = setInterval(() => {
      const isBuy = Math.random() > 0.48;
      const tPrice = isBuy
        ? markPrice + Math.random() * 2
        : markPrice - Math.random() * 2;
      const newTrade: TradeTick = {
        id: `trade-${Date.now()}`,
        price: Number(tPrice.toFixed(2)),
        size: Number((Math.random() * 2.2 + 0.05).toFixed(3)),
        side: isBuy ? 'buy' : 'sell',
        time: new Date().toLocaleTimeString([], {
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
        }),
      };

      setRecentTrades((prev) => [newTrade, ...prev.slice(0, 15)]);
    }, 1800);

    return () => clearInterval(interval);
  }, [markPrice, bestAsk, bestBid]);

  return (
    <div className="bg-[#0b0f19] border-t border-slate-800/80 p-2 text-xs font-mono select-none">
      {/* Tab Header */}
      <div className="flex items-center justify-between pb-1.5 border-b border-slate-800/60 mb-2">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setActiveTab('depth')}
            className={`px-2 py-0.5 rounded text-[11px] font-semibold transition-all ${
              activeTab === 'depth'
                ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/40'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            Order Book
          </button>
          <button
            onClick={() => setActiveTab('trades')}
            className={`px-2 py-0.5 rounded text-[11px] font-semibold transition-all ${
              activeTab === 'trades'
                ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/40'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            Recent Trades
          </button>
        </div>

        <div className="text-[10px] text-slate-400">
          Spread:{' '}
          <span className="text-slate-200 font-bold">
            ${spread.toFixed(2)} ({spreadPercent.toFixed(3)}%)
          </span>
        </div>
      </div>

      {activeTab === 'depth' ? (
        <div>
          {/* Table Headers */}
          <div className="grid grid-cols-3 text-[10px] text-slate-500 pb-1 px-1">
            <span>Price (USD)</span>
            <span className="text-right">Size ({symbol.startsWith('BTC') ? 'BTC' : 'ETH'})</span>
            <span className="text-right">Total Depth</span>
          </div>

          {/* Asks (Sells - Red) */}
          <div className="space-y-0.5">
            {asks.slice(0, 5).map((a, i) => {
              const depthPct = Math.min(100, (a.total / maxTotal) * 100);
              return (
                <div
                  key={`ask-${i}`}
                  onClick={() => onQuickTrade && onQuickTrade('SHORT', a.price)}
                  className="grid grid-cols-3 py-0.5 px-1 relative text-[11px] hover:bg-rose-500/10 cursor-pointer rounded transition-colors"
                >
                  <div
                    className="absolute inset-y-0 right-0 bg-rose-500/10 pointer-events-none rounded"
                    style={{ width: `${depthPct}%` }}
                  />
                  <span className="text-rose-400 font-medium z-10">${a.price.toFixed(2)}</span>
                  <span className="text-right text-slate-300 z-10">{a.size.toFixed(3)}</span>
                  <span className="text-right text-slate-400 z-10">{a.total.toFixed(2)}</span>
                </div>
              );
            })}
          </div>

          {/* Mid Market Price Flash Banner */}
          <div className="my-1.5 py-1 px-2 bg-slate-900/90 rounded border border-slate-800 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-[10px] text-slate-400">Mark:</span>
              <span className="text-sm font-bold text-cyan-400">${markPrice.toFixed(2)}</span>
            </div>
            <div className="text-[10px] text-emerald-400 flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping"></span>
              Live Matching
            </div>
          </div>

          {/* Bids (Buys - Green) */}
          <div className="space-y-0.5">
            {bids.slice(0, 5).map((b, i) => {
              const depthPct = Math.min(100, (b.total / maxTotal) * 100);
              return (
                <div
                  key={`bid-${i}`}
                  onClick={() => onQuickTrade && onQuickTrade('LONG', b.price)}
                  className="grid grid-cols-3 py-0.5 px-1 relative text-[11px] hover:bg-emerald-500/10 cursor-pointer rounded transition-colors"
                >
                  <div
                    className="absolute inset-y-0 right-0 bg-emerald-500/10 pointer-events-none rounded"
                    style={{ width: `${depthPct}%` }}
                  />
                  <span className="text-emerald-400 font-medium z-10">${b.price.toFixed(2)}</span>
                  <span className="text-right text-slate-300 z-10">{b.size.toFixed(3)}</span>
                  <span className="text-right text-slate-400 z-10">{b.total.toFixed(2)}</span>
                </div>
              );
            })}
          </div>
        </div>
      ) : (
        /* Recent Trades Stream */
        <div className="space-y-1 max-h-[170px] overflow-y-auto">
          <div className="grid grid-cols-3 text-[10px] text-slate-500 pb-1 px-1">
            <span>Price (USD)</span>
            <span className="text-right">Size</span>
            <span className="text-right">Time</span>
          </div>
          {recentTrades.map((t) => (
            <div
              key={t.id}
              className="grid grid-cols-3 py-0.5 px-1 text-[11px] border-b border-slate-800/30"
            >
              <span className={t.side === 'buy' ? 'text-emerald-400' : 'text-rose-400'}>
                ${t.price.toFixed(2)}
              </span>
              <span className="text-right text-slate-300">{t.size.toFixed(3)}</span>
              <span className="text-right text-slate-400">{t.time}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
