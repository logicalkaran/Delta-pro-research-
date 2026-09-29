import React, { useState } from 'react';
import {
  Star,
  Search,
  TrendingUp,
  TrendingDown,
  Bell,
  BarChart2,
  Cpu,
  Flame,
  Filter,
} from 'lucide-react';
import { Ticker } from '../types/crypto';

interface WatchlistProps {
  tickers: Ticker[];
  favorites: string[];
  onToggleFavorite: (symbol: string) => void;
  onSelectSymbol: (symbol: string) => void;
  onOpenAlertModal: (symbol: string) => void;
  onOpenAlgo: (symbol: string) => void;
  selectedSymbol: string;
}

export const Watchlist: React.FC<WatchlistProps> = ({
  tickers,
  favorites,
  onToggleFavorite,
  onSelectSymbol,
  onOpenAlertModal,
  onOpenAlgo,
  selectedSymbol,
}) => {
  const [filterTab, setFilterTab] = useState<'all' | 'favorites' | 'btc' | 'eth' | 'options'>(
    'all'
  );
  const [searchQuery, setSearchQuery] = useState('');

  // Filter tickers
  const filtered = tickers.filter((t) => {
    const matchesSearch =
      t.symbol.toLowerCase().includes(searchQuery.toLowerCase()) ||
      t.name.toLowerCase().includes(searchQuery.toLowerCase());
    if (!matchesSearch) return false;

    if (filterTab === 'favorites') return favorites.includes(t.symbol);
    if (filterTab === 'btc') return t.underlying_asset === 'BTC';
    if (filterTab === 'eth') return t.underlying_asset === 'ETH';
    if (filterTab === 'options')
      return t.contract_type === 'call_options' || t.contract_type === 'put_options';

    return true;
  });

  return (
    <div className="flex flex-col h-full bg-[#080c14] select-none text-slate-100">
      {/* Header & Search */}
      <div className="p-3 bg-[#0d121f] border-b border-slate-800/80 space-y-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-md bg-cyan-600/30 border border-cyan-500/50 flex items-center justify-center">
              <Flame className="w-3.5 h-3.5 text-cyan-400" />
            </div>
            <h2 className="font-bold text-sm text-white tracking-wide">Delta Markets & Watchlist</h2>
          </div>
          <span className="text-[11px] font-mono text-slate-400 bg-slate-800 px-2 py-0.5 rounded-full border border-slate-700">
            {filtered.length} Markets
          </span>
        </div>

        {/* Search Input */}
        <div className="relative">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            placeholder="Search BTC, ETH, Options or Perps..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-[#07090e] border border-slate-800 rounded-xl pl-9 pr-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500/60 font-mono transition-colors"
          />
        </div>

        {/* Filter Tabs */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-0.5 text-xs">
          <button
            onClick={() => setFilterTab('all')}
            className={`px-2.5 py-1 rounded-lg text-[11px] font-medium transition-all ${
              filterTab === 'all'
                ? 'bg-cyan-500 text-slate-950 font-bold shadow-sm shadow-cyan-500/30'
                : 'bg-slate-800/80 text-slate-300 hover:bg-slate-700'
            }`}
          >
            All
          </button>
          <button
            onClick={() => setFilterTab('favorites')}
            className={`flex items-center gap-1 px-2.5 py-1 rounded-lg text-[11px] font-medium transition-all ${
              filterTab === 'favorites'
                ? 'bg-amber-500 text-slate-950 font-bold shadow-sm shadow-amber-500/30'
                : 'bg-slate-800/80 text-slate-300 hover:bg-slate-700'
            }`}
          >
            <Star className="w-3 h-3 fill-current" />
            <span>Favorites ({favorites.length})</span>
          </button>
          <button
            onClick={() => setFilterTab('btc')}
            className={`px-2.5 py-1 rounded-lg text-[11px] font-medium transition-all ${
              filterTab === 'btc'
                ? 'bg-cyan-500 text-slate-950 font-bold'
                : 'bg-slate-800/80 text-slate-300 hover:bg-slate-700'
            }`}
          >
            BTC
          </button>
          <button
            onClick={() => setFilterTab('eth')}
            className={`px-2.5 py-1 rounded-lg text-[11px] font-medium transition-all ${
              filterTab === 'eth'
                ? 'bg-cyan-500 text-slate-950 font-bold'
                : 'bg-slate-800/80 text-slate-300 hover:bg-slate-700'
            }`}
          >
            ETH
          </button>
          <button
            onClick={() => setFilterTab('options')}
            className={`px-2.5 py-1 rounded-lg text-[11px] font-medium transition-all ${
              filterTab === 'options'
                ? 'bg-cyan-500 text-slate-950 font-bold'
                : 'bg-slate-800/80 text-slate-300 hover:bg-slate-700'
            }`}
          >
            Options
          </button>
        </div>
      </div>

      {/* Markets List */}
      <div className="flex-1 overflow-y-auto divide-y divide-slate-800/50 p-2 space-y-1">
        {filtered.length === 0 ? (
          <div className="text-center py-12 text-slate-500 text-xs">
            <Filter className="w-8 h-8 mx-auto mb-2 opacity-40" />
            <p>No contracts match your search filter.</p>
          </div>
        ) : (
          filtered.map((ticker) => {
            const isFav = favorites.includes(ticker.symbol);
            const isSelected = ticker.symbol === selectedSymbol;
            const isOption =
              ticker.contract_type === 'call_options' || ticker.contract_type === 'put_options';

            return (
              <div
                key={ticker.symbol}
                className={`p-2.5 rounded-xl border transition-all ${
                  isSelected
                    ? 'bg-cyan-950/30 border-cyan-500/40 shadow-sm'
                    : 'bg-[#0d121e]/70 border-slate-800/60 hover:border-slate-700/80'
                }`}
              >
                <div className="flex items-center justify-between">
                  {/* Left: Star + Symbol Info */}
                  <div className="flex items-center gap-2">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onToggleFavorite(ticker.symbol);
                      }}
                      className="p-1 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-amber-400 transition-colors"
                      title={isFav ? 'Remove from favorites' : 'Add to favorites'}
                    >
                      <Star
                        className={`w-4 h-4 ${
                          isFav ? 'text-amber-400 fill-amber-400' : 'text-slate-500'
                        }`}
                      />
                    </button>

                    <div
                      className="cursor-pointer"
                      onClick={() => onSelectSymbol(ticker.symbol)}
                    >
                      <div className="flex items-center gap-1.5">
                        <span className="font-bold text-sm text-white font-mono">
                          {ticker.symbol}
                        </span>
                        <span
                          className={`text-[9px] px-1 rounded font-mono font-medium ${
                            isOption
                              ? 'bg-purple-950 text-purple-300 border border-purple-800/50'
                              : 'bg-cyan-950 text-cyan-300 border border-cyan-800/50'
                          }`}
                        >
                          {isOption ? 'OPTION' : 'PERP'}
                        </span>
                      </div>
                      <p className="text-[11px] text-slate-400 truncate max-w-[150px]">
                        {ticker.name}
                      </p>
                    </div>
                  </div>

                  {/* Right: Price & 24h Change */}
                  <div
                    className="text-right cursor-pointer"
                    onClick={() => onSelectSymbol(ticker.symbol)}
                  >
                    <div className="font-bold text-sm font-mono text-white">
                      $
                      {ticker.mark_price >= 1000
                        ? ticker.mark_price.toLocaleString(undefined, {
                            minimumFractionDigits: 1,
                            maximumFractionDigits: 1,
                          })
                        : ticker.mark_price.toLocaleString(undefined, {
                            minimumFractionDigits: 2,
                            maximumFractionDigits: 2,
                          })}
                    </div>
                    <span
                      className={`inline-flex items-center text-[10px] font-mono font-semibold px-1.5 py-0.2 rounded mt-0.5 ${
                        ticker.change_24h_percent >= 0
                          ? 'bg-emerald-500/15 text-emerald-400'
                          : 'bg-rose-500/15 text-rose-400'
                      }`}
                    >
                      {ticker.change_24h_percent >= 0 ? '+' : ''}
                      {ticker.change_24h_percent.toFixed(2)}%
                    </span>
                  </div>
                </div>

                {/* Sub row: Quick statistics & Fast Actions */}
                <div className="mt-2 pt-1.5 border-t border-slate-800/60 flex items-center justify-between text-[10px] font-mono text-slate-400">
                  <div className="flex items-center gap-3">
                    <span>
                      24h Vol:{' '}
                      <span className="text-slate-300">
                        {ticker.volume_24h > 1000
                          ? `${(ticker.volume_24h / 1000).toFixed(1)}K`
                          : ticker.volume_24h.toFixed(0)}
                      </span>
                    </span>
                    {!isOption && (
                      <span>
                        Funding:{' '}
                        <span
                          className={
                            ticker.funding_rate >= 0 ? 'text-emerald-400' : 'text-rose-400'
                          }
                        >
                          {(ticker.funding_rate * 100).toFixed(3)}%
                        </span>
                      </span>
                    )}
                  </div>

                  {/* Fast Action Buttons */}
                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => onSelectSymbol(ticker.symbol)}
                      className="px-2 py-0.5 rounded bg-slate-800 hover:bg-cyan-600 hover:text-white text-slate-300 transition-colors flex items-center gap-1"
                      title="Open Interactive Chart"
                    >
                      <BarChart2 className="w-3 h-3" />
                      <span>Chart</span>
                    </button>
                    <button
                      onClick={() => onOpenAlertModal(ticker.symbol)}
                      className="px-2 py-0.5 rounded bg-slate-800 hover:bg-amber-600 hover:text-white text-slate-300 transition-colors flex items-center gap-1"
                      title="Set Price Alert"
                    >
                      <Bell className="w-3 h-3" />
                      <span>Alert</span>
                    </button>
                    <button
                      onClick={() => onOpenAlgo(ticker.symbol)}
                      className="px-2 py-0.5 rounded bg-slate-800 hover:bg-purple-600 hover:text-white text-slate-300 transition-colors flex items-center gap-1"
                      title="Run Algo Strategy"
                    >
                      <Cpu className="w-3 h-3" />
                      <span>Algo</span>
                    </button>
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
