import React, { useState } from 'react';
import {
  Layers,
  ArrowUpDown,
  ShieldCheck,
  TrendingUp,
  AlertTriangle,
  Info,
  Sliders,
} from 'lucide-react';
import { OrderBookState } from '../types/microstructure';

interface OrderBookReconstructionViewProps {
  orderBooks: OrderBookState[];
}

export const OrderBookReconstructionView: React.FC<OrderBookReconstructionViewProps> = ({
  orderBooks,
}) => {
  const currentBook = orderBooks.length > 0 ? orderBooks[orderBooks.length - 1] : null;
  const [depthLevelsCount, setDepthLevelsCount] = useState<number>(10);

  if (!currentBook) {
    return (
      <div className="p-8 text-center text-slate-500 font-mono text-xs">
        No reconstructed order book state available. Ingest market data to view book depth.
      </div>
    );
  }

  const bids = currentBook.bids.slice(0, depthLevelsCount);
  const asks = currentBook.asks.slice(0, depthLevelsCount);

  // Compute maximum cumulative volume for visual bars
  const maxBidTotal = bids.reduce((sum, b) => sum + b.size, 0);
  const maxAskTotal = asks.reduce((sum, a) => sum + a.size, 0);
  const maxTotal = Math.max(maxBidTotal, maxAskTotal, 0.001);

  // Microprice displacement from midprice
  const micropriceDiff = currentBook.microprice - currentBook.midPrice;
  const micropriceDiffBps = currentBook.midPrice > 0 ? (micropriceDiff / currentBook.midPrice) * 10000 : 0;

  return (
    <div className="p-4 sm:p-6 space-y-5 max-w-7xl mx-auto text-slate-100 font-mono">
      {/* Module Title Banner */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 p-4 rounded-2xl bg-[#0d121f] border border-slate-800">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-purple-500/20 border border-purple-500/40 flex items-center justify-center">
            <Layers className="w-4 h-4 text-purple-400" />
          </div>
          <div>
            <h2 className="font-bold text-sm text-white font-sans">
              Order-Book Reconstruction & Microstructure Metrics
            </h2>
            <p className="text-[11px] text-slate-400 font-sans">
              Reconstructed L2 state, volume-weighted microprice, depth imbalance, and liquidity concentration
            </p>
          </div>
        </div>

        {/* Depth Level Selector */}
        <div className="flex items-center gap-2 text-xs">
          <span className="text-slate-400 font-sans">Display Depth:</span>
          {[5, 10, 20].map((lvl) => (
            <button
              key={lvl}
              onClick={() => setDepthLevelsCount(lvl)}
              className={`px-2.5 py-1 rounded-lg transition-all ${
                depthLevelsCount === lvl
                  ? 'bg-purple-600 text-white font-bold'
                  : 'bg-slate-800 text-slate-400 hover:text-white'
              }`}
            >
              Top {lvl}
            </button>
          ))}
        </div>
      </div>

      {/* 4 Microstructure Metric Panels */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
        {/* Microprice */}
        <div className="p-3.5 bg-[#0d121f] rounded-2xl border border-slate-800 space-y-1">
          <div className="flex items-center justify-between text-slate-400">
            <span>VOLUME MICROPRICE</span>
            <span className={micropriceDiff >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
              {micropriceDiff >= 0 ? '+' : ''}{micropriceDiffBps.toFixed(2)} bps
            </span>
          </div>
          <div className="text-xl font-bold text-white">${currentBook.microprice.toLocaleString()}</div>
          <div className="text-[11px] text-slate-400">Mid: ${currentBook.midPrice.toLocaleString()}</div>
        </div>

        {/* Spread Bps */}
        <div className="p-3.5 bg-[#0d121f] rounded-2xl border border-slate-800 space-y-1">
          <div className="flex items-center justify-between text-slate-400">
            <span>SPREAD (USD / BPS)</span>
            <span className="text-cyan-400 font-bold">{currentBook.spreadBps} bps</span>
          </div>
          <div className="text-xl font-bold text-cyan-400">${currentBook.spread.toFixed(2)}</div>
          <div className="text-[11px] text-slate-400">Best Bid: ${currentBook.bestBid} • Ask: ${currentBook.bestAsk}</div>
        </div>

        {/* Depth Imbalance (Top 10) */}
        <div className="p-3.5 bg-[#0d121f] rounded-2xl border border-slate-800 space-y-1">
          <div className="flex items-center justify-between text-slate-400">
            <span>DEPTH IMBALANCE (L10)</span>
            <span className={currentBook.depthImbalance10 >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
              {currentBook.depthImbalance10 >= 0 ? 'BUY HEAVY' : 'SELL HEAVY'}
            </span>
          </div>
          <div className={`text-xl font-bold ${currentBook.depthImbalance10 >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
            {currentBook.depthImbalance10 >= 0 ? '+' : ''}{(currentBook.depthImbalance10 * 100).toFixed(1)}%
          </div>
          <div className="text-[11px] text-slate-400">
            Bid: {currentBook.bidDepth10.toFixed(2)} BTC • Ask: {currentBook.askDepth10.toFixed(2)} BTC
          </div>
        </div>

        {/* Liquidity Concentration */}
        <div className="p-3.5 bg-[#0d121f] rounded-2xl border border-slate-800 space-y-1">
          <div className="flex items-center justify-between text-slate-400">
            <span>LIQUIDITY CONCENTRATION</span>
            <span className="text-purple-400">Top 3 / Top 20</span>
          </div>
          <div className="text-xl font-bold text-purple-400">
            {(currentBook.liquidityConcentration * 100).toFixed(1)}%
          </div>
          <div className="text-[11px] text-slate-400">
            {currentBook.isCrossed ? (
              <span className="text-rose-400 font-bold flex items-center gap-1">
                <AlertTriangle className="w-3 h-3" /> Crossed Book!
              </span>
            ) : (
              <span className="text-emerald-400 flex items-center gap-1">
                <ShieldCheck className="w-3 h-3" /> Valid Order Book
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Multi-Level Imbalance Comparison Bar */}
      <div className="p-4 rounded-2xl bg-[#0d121f] border border-slate-800 space-y-2">
        <span className="font-bold text-xs text-white block font-sans">
          Multi-Tier Depth Imbalance Structure (L5 vs L10 vs L20)
        </span>
        <div className="grid grid-cols-3 gap-3 text-xs">
          <div className="p-2.5 rounded-xl bg-[#090d16] border border-slate-800 text-center">
            <span className="text-[10px] text-slate-500 block">TOP 5 LEVELS</span>
            <span className={`text-base font-bold ${currentBook.depthImbalance5 >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
              {currentBook.depthImbalance5 > 0 ? '+' : ''}{(currentBook.depthImbalance5 * 100).toFixed(1)}%
            </span>
          </div>
          <div className="p-2.5 rounded-xl bg-[#090d16] border border-slate-800 text-center">
            <span className="text-[10px] text-slate-500 block">TOP 10 LEVELS</span>
            <span className={`text-base font-bold ${currentBook.depthImbalance10 >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
              {currentBook.depthImbalance10 > 0 ? '+' : ''}{(currentBook.depthImbalance10 * 100).toFixed(1)}%
            </span>
          </div>
          <div className="p-2.5 rounded-xl bg-[#090d16] border border-slate-800 text-center">
            <span className="text-[10px] text-slate-500 block">TOP 20 LEVELS</span>
            <span className={`text-base font-bold ${currentBook.depthImbalance20 >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
              {currentBook.depthImbalance20 > 0 ? '+' : ''}{(currentBook.depthImbalance20 * 100).toFixed(1)}%
            </span>
          </div>
        </div>
      </div>

      {/* Reconstructed L2 Order Book Ladder */}
      <div className="p-4 rounded-2xl bg-[#0d121f] border border-slate-800 space-y-2">
        <div className="flex items-center justify-between pb-2 border-b border-slate-800">
          <span className="font-bold text-xs text-white font-sans">
            Reconstructed L2 Order-Book Ladder (Depth {depthLevelsCount})
          </span>
          <span className="text-xs text-slate-400">
            Timestamp: {new Date(currentBook.timestamp).toLocaleTimeString()}
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
          {/* Asks (Sells) */}
          <div className="space-y-1">
            <div className="flex justify-between text-[10px] text-slate-500 px-1 border-b border-slate-800 pb-1">
              <span>ASK PRICE (USD)</span>
              <span>SIZE (BTC)</span>
              <span>CUMULATIVE</span>
            </div>
            <div className="space-y-0.5">
              {[...asks].reverse().map((a, idx) => {
                const cumSize = asks.slice(0, asks.length - idx).reduce((s, x) => s + x.size, 0);
                const widthPct = Math.min(100, (cumSize / maxTotal) * 100);
                return (
                  <div
                    key={`ask-${a.price}`}
                    className="flex items-center justify-between p-1 rounded relative hover:bg-rose-500/10 transition-colors"
                  >
                    <div
                      className="absolute inset-y-0 right-0 bg-rose-500/15 pointer-events-none rounded"
                      style={{ width: `${widthPct}%` }}
                    />
                    <span className="text-rose-400 font-bold z-10">${a.price.toFixed(2)}</span>
                    <span className="text-slate-300 z-10">{a.size.toFixed(4)}</span>
                    <span className="text-slate-400 z-10">{cumSize.toFixed(4)}</span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Bids (Buys) */}
          <div className="space-y-1">
            <div className="flex justify-between text-[10px] text-slate-500 px-1 border-b border-slate-800 pb-1">
              <span>BID PRICE (USD)</span>
              <span>SIZE (BTC)</span>
              <span>CUMULATIVE</span>
            </div>
            <div className="space-y-0.5">
              {bids.map((b, idx) => {
                const cumSize = bids.slice(0, idx + 1).reduce((s, x) => s + x.size, 0);
                const widthPct = Math.min(100, (cumSize / maxTotal) * 100);
                return (
                  <div
                    key={`bid-${b.price}`}
                    className="flex items-center justify-between p-1 rounded relative hover:bg-emerald-500/10 transition-colors"
                  >
                    <div
                      className="absolute inset-y-0 right-0 bg-emerald-500/15 pointer-events-none rounded"
                      style={{ width: `${widthPct}%` }}
                    />
                    <span className="text-emerald-400 font-bold z-10">${b.price.toFixed(2)}</span>
                    <span className="text-slate-300 z-10">{b.size.toFixed(4)}</span>
                    <span className="text-slate-400 z-10">{cumSize.toFixed(4)}</span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
