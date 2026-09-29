import React, { useState, useEffect } from 'react';
import {
  Wifi,
  Battery,
  SignalHigh,
  TrendingUp,
  BarChart2,
  Bell,
  PieChart,
  Cpu,
  Smartphone,
  Maximize2,
  X,
  Volume2,
  Sparkles,
  Download,
} from 'lucide-react';
import { AlertNotification } from '../types/crypto';

interface AndroidFrameProps {
  children: React.ReactNode;
  activeTab: 'markets' | 'chart' | 'alerts' | 'dashboard' | 'algo';
  setActiveTab: (tab: 'markets' | 'chart' | 'alerts' | 'dashboard' | 'algo') => void;
  activeNotifications: AlertNotification[];
  onDismissNotification: (id: string) => void;
  selectedSymbol: string;
  sourceType: string;
  unreadAlertCount: number;
  onOpenDownloadModal: () => void;
}

export const AndroidFrame: React.FC<AndroidFrameProps> = ({
  children,
  activeTab,
  setActiveTab,
  activeNotifications,
  onDismissNotification,
  selectedSymbol,
  sourceType,
  unreadAlertCount,
  onOpenDownloadModal,
}) => {
  const [currentTime, setCurrentTime] = useState('');
  const [isPhoneFrame, setIsPhoneFrame] = useState(true);

  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      setCurrentTime(
        now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false })
      );
    };
    updateTime();
    const interval = setInterval(updateTime, 1000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="min-h-screen bg-[#07090e] text-slate-100 flex flex-col items-center justify-start p-0 sm:p-4 select-none">
      {/* Desktop Toolbar: Toggle Phone Mockup vs Full Responsive View */}
      <header className="hidden sm:flex items-center justify-between w-full max-w-5xl mb-3 px-4 py-2 bg-[#0d121f] border border-slate-800/80 rounded-xl shadow-lg">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-cyan-600 via-blue-600 to-indigo-600 flex items-center justify-center shadow-md shadow-cyan-500/20">
            <span className="font-bold text-white tracking-tighter text-sm">Δ</span>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-bold text-sm text-white tracking-wide">DELTA PRO</span>
              <span className="text-[10px] px-1.5 py-0.5 rounded font-mono font-medium bg-cyan-500/10 text-cyan-400 border border-cyan-500/30">
                ANDROID TRADER
              </span>
              <span className="flex items-center gap-1 text-[11px] text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/20">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                {sourceType === 'delta_live' ? 'DELTA API LIVE' : 'SYNC FEED LIVE'}
              </span>
            </div>
            <p className="text-xs text-slate-400">
              Bitcoin & ETH Perpetuals, Volatility Options, Algo Backtester & AI Copilot
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={onOpenDownloadModal}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold bg-cyan-500 hover:bg-cyan-400 text-slate-950 shadow-md shadow-cyan-500/25 transition-all"
            title="Download & Install as Android / Desktop app"
          >
            <Download className="w-3.5 h-3.5" />
            <span>Download App</span>
          </button>

          <button
            onClick={() => setIsPhoneFrame(!isPhoneFrame)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
              isPhoneFrame
                ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-sm'
                : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
            }`}
            title="Toggle Android Device Frame view"
          >
            {isPhoneFrame ? (
              <>
                <Smartphone className="w-3.5 h-3.5 text-cyan-400" />
                <span>Pixel Frame View</span>
              </>
            ) : (
              <>
                <Maximize2 className="w-3.5 h-3.5 text-slate-300" />
                <span>Expanded View</span>
              </>
            )}
          </button>
        </div>
      </header>

      {/* Main Container - Android Phone Shell or Edge-to-Edge */}
      <main
        className={`w-full transition-all duration-300 relative flex flex-col ${
          isPhoneFrame
            ? 'max-w-[440px] h-[92vh] max-h-[880px] bg-[#0b0e17] sm:rounded-[44px] sm:border-[8px] sm:border-slate-800 sm:shadow-[0_25px_60px_-15px_rgba(0,0,0,0.9),0_0_35px_rgba(6,182,212,0.12)] overflow-hidden'
            : 'max-w-6xl h-auto min-h-[88vh] bg-[#0b0e17] rounded-2xl border border-slate-800/80 shadow-2xl overflow-hidden'
        }`}
      >
        {/* Android Camera Notch & Speaker (Only in phone frame view) */}
        {isPhoneFrame && (
          <div className="hidden sm:flex absolute top-0 left-1/2 -translate-x-1/2 z-50 items-center justify-center pt-2">
            <div className="w-24 h-4 bg-slate-900 rounded-b-xl flex items-center justify-center gap-3 border-b border-x border-slate-800/60 shadow-inner">
              <div className="w-10 h-1 bg-slate-700/80 rounded-full"></div>
              <div className="w-2.5 h-2.5 rounded-full bg-slate-950 border border-slate-800 flex items-center justify-center">
                <div className="w-1 h-1 rounded-full bg-blue-500/70"></div>
              </div>
            </div>
          </div>
        )}

        {/* Android Status Bar */}
        <div className="w-full bg-[#090c13] px-4 pt-2 pb-1.5 flex items-center justify-between text-xs font-mono text-slate-300 z-40 border-b border-slate-800/40 shrink-0">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-slate-200 tracking-wider">
              {currentTime || '12:00'}
            </span>
            <button
              onClick={onOpenDownloadModal}
              className="flex items-center gap-1 text-[10px] px-1.5 py-0.2 rounded bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 hover:bg-cyan-500/30 transition-all font-sans font-semibold"
              title="Download & Install app on Android"
            >
              <Download className="w-2.5 h-2.5" />
              <span>Install</span>
            </button>
          </div>
          <div className="flex items-center gap-2 text-slate-400">
            <span className="text-[10px] font-bold text-cyan-400 bg-cyan-950/60 px-1 rounded border border-cyan-800/50">
              5G
            </span>
            <SignalHigh className="w-3.5 h-3.5 text-slate-300" />
            <Wifi className="w-3.5 h-3.5 text-slate-300" />
            <div className="flex items-center gap-1 text-[11px] text-slate-200">
              <span>96%</span>
              <Battery className="w-4 h-4 text-emerald-400 fill-emerald-400/30" />
            </div>
          </div>
        </div>

        {/* Android Push Notification Banner (Floats at top of device) */}
        <div className="absolute top-10 left-3 right-3 z-50 pointer-events-none space-y-2">
          {activeNotifications.slice(0, 2).map((notif) => (
            <div
              key={notif.id}
              className="pointer-events-auto bg-[#121826]/95 backdrop-blur-md border border-cyan-500/50 p-3 rounded-2xl shadow-2xl shadow-cyan-950/50 flex items-start gap-3 animate-in slide-in-from-top duration-300"
            >
              <div className="w-9 h-9 rounded-xl bg-cyan-500/20 border border-cyan-500/40 flex items-center justify-center shrink-0">
                <Volume2 className="w-4 h-4 text-cyan-300 animate-bounce" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5">
                    <span className="font-bold text-xs text-white">{notif.title}</span>
                    <span className="text-[10px] px-1 py-0.2 rounded bg-amber-500/20 text-amber-300 font-mono">
                      TRIGGERED
                    </span>
                  </div>
                  <button
                    onClick={() => onDismissNotification(notif.id)}
                    className="text-slate-400 hover:text-white p-0.5 rounded-lg"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>
                <p className="text-xs text-slate-300 mt-0.5 truncate">{notif.message}</p>
                <div className="flex items-center justify-between mt-1 text-[10px] font-mono text-cyan-400">
                  <span>Price: ${notif.price.toLocaleString()}</span>
                  <span className="text-slate-500">Just now</span>
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Dynamic Screen Content (Scrollable) */}
        <div className="flex-1 overflow-y-auto overflow-x-hidden flex flex-col relative bg-[#090c13]">
          {children}
        </div>

        {/* Android Bottom App Navigation Bar */}
        <nav aria-label="Bottom Navigation" className="w-full bg-[#0b0f19] border-t border-slate-800/80 px-2 py-1.5 flex items-center justify-around z-30 shrink-0 shadow-lg">
          <button
            onClick={() => setActiveTab('markets')}
            className={`flex flex-col items-center gap-0.5 py-1 px-2.5 rounded-xl transition-all ${
              activeTab === 'markets'
                ? 'text-cyan-400 bg-cyan-500/10'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <TrendingUp className="w-4 h-4" />
            <span className="text-[10px] font-medium tracking-tight">Watchlist</span>
          </button>

          <button
            onClick={() => setActiveTab('chart')}
            className={`flex flex-col items-center gap-0.5 py-1 px-2.5 rounded-xl transition-all ${
              activeTab === 'chart'
                ? 'text-cyan-400 bg-cyan-500/10'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <BarChart2 className="w-4 h-4" />
            <span className="text-[10px] font-medium tracking-tight">Chart</span>
          </button>

          <button
            onClick={() => setActiveTab('alerts')}
            className={`flex flex-col items-center gap-0.5 py-1 px-2.5 rounded-xl relative transition-all ${
              activeTab === 'alerts'
                ? 'text-cyan-400 bg-cyan-500/10'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Bell className="w-4 h-4" />
            {unreadAlertCount > 0 && (
              <span className="absolute top-1 right-2 w-2 h-2 rounded-full bg-rose-500 animate-pulse"></span>
            )}
            <span className="text-[10px] font-medium tracking-tight">Alerts</span>
          </button>

          <button
            onClick={() => setActiveTab('dashboard')}
            className={`flex flex-col items-center gap-0.5 py-1 px-2.5 rounded-xl transition-all ${
              activeTab === 'dashboard'
                ? 'text-cyan-400 bg-cyan-500/10'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <PieChart className="w-4 h-4" />
            <span className="text-[10px] font-medium tracking-tight">Analytics</span>
          </button>

          <button
            onClick={() => setActiveTab('algo')}
            className={`flex flex-col items-center gap-0.5 py-1 px-2.5 rounded-xl transition-all ${
              activeTab === 'algo'
                ? 'text-cyan-400 bg-cyan-500/10'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <div className="relative">
              <Cpu className="w-4 h-4" />
              <Sparkles className="w-2.5 h-2.5 text-amber-400 absolute -top-1 -right-1.5" />
            </div>
            <span className="text-[10px] font-medium tracking-tight">Algo & AI</span>
          </button>
        </nav>

        {/* Android System Navigation Pill / Back Gesture Bar */}
        <div className="w-full bg-[#0b0f19] py-1.5 flex items-center justify-center shrink-0 border-t border-slate-900">
          <div className="w-28 h-1 bg-slate-600/70 rounded-full hover:bg-slate-400 transition-colors cursor-pointer"></div>
        </div>
      </main>
    </div>
  );
};
