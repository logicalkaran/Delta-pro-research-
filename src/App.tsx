/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 *
 * PROJECT: DELTA RESEARCH & INDICATOR ENGINE V2
 * Quantitative Microstructure Analytics & Indicator Development Platform
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { ResearchHeader, ResearchTabType } from './components/ResearchHeader';
import { OverviewView } from './components/OverviewView';
import { DataExplorerView } from './components/DataExplorerView';
import { OrderBookReconstructionView } from './components/OrderBookReconstructionView';
import { DeltaAnalyticsView } from './components/DeltaAnalyticsView';
import { ResearchLabView } from './components/ResearchLabView';
import { IndicatorWorkbenchView } from './components/IndicatorWorkbenchView';
import { IndicatorBuilderView } from './components/IndicatorBuilderView';
import { ValidationReportsView } from './components/ValidationReportsView';
import { IndicatorRegistryView } from './components/IndicatorRegistryView';
import { DataQualityView } from './components/DataQualityView';
import { SettingsAndBridgeView } from './components/SettingsAndBridgeView';

// Production Trading & Mobile Terminal Components (Preserved)
import { AndroidFrame } from './components/AndroidFrame';
import { InteractiveChart } from './components/InteractiveChart';
import { OrderBook } from './components/OrderBook';
import { Watchlist } from './components/Watchlist';
import { AlertsManager } from './components/AlertsManager';
import { MarketAnalysisDashboard } from './components/MarketAnalysisDashboard';
import { AlgoTradingStudio } from './components/AlgoTradingStudio';
import { DownloadModal } from './components/DownloadModal';

import {
  Ticker,
  Candle,
  AlertRule,
  AlertNotification,
  BacktestResult,
  BacktestTrade,
  Position,
  GeminiMarketAnalysis,
} from './types/crypto';
import {
  TradeEvent,
  OrderBookState,
  DeltaBar,
  DataQualityReport,
  IndicatorDefinition,
  IndicatorLifecycleStatus,
  ResearchExperimentResult,
} from './types/microstructure';
import { generateSyntheticMicrostructureData } from './utils/syntheticDataGenerator';
import { validateMarketDataBatch } from './utils/dataQualityValidator';
import { aggregateTradesIntoDeltaBars } from './utils/deltaEngine';
import { INITIAL_RESEARCH_INDICATORS } from './utils/registeredIndicators';
import { playAlertNotificationSound } from './utils/indicators';
import { Layers, Terminal, Sparkles, Smartphone, BarChart2 } from 'lucide-react';

export default function App() {
  // Mode: 'research' (Quantitative Workstation) or 'terminal' (Live Execution & Mobile Frame)
  const [appMode, setAppMode] = useState<'research' | 'terminal'>('research');
  const [researchTab, setResearchTab] = useState<ResearchTabType>('overview');
  const [datasetId, setDatasetId] = useState<string>('BTCUSDT-L2-SYNTH-240M');
  const [symbol, setSymbol] = useState<string>('BTCUSD');

  // Microstructure Research Datasets
  const [microData, setMicroData] = useState(() => generateSyntheticMicrostructureData(240, 94350));
  const [qualityReport, setQualityReport] = useState<DataQualityReport>(() => {
    const { report } = validateMarketDataBatch(microData.rawJsonlLines);
    return report;
  });

  // Indicator Registry
  const [indicators, setIndicators] = useState<IndicatorDefinition[]>(() => {
    try {
      const saved = localStorage.getItem('deltapro_v2_indicators');
      return saved ? JSON.parse(saved) : INITIAL_RESEARCH_INDICATORS;
    } catch (e) {
      return INITIAL_RESEARCH_INDICATORS;
    }
  });

  // Latest Experiment Result
  const [latestExperiment, setLatestExperiment] = useState<ResearchExperimentResult | null>(null);

  // Download & Modal State
  const [isDownloadModalOpen, setIsDownloadModalOpen] = useState<boolean>(false);

  // Preserved Live Trading Terminal State
  const [terminalTab, setTerminalTab] = useState<'markets' | 'chart' | 'alerts' | 'dashboard' | 'algo'>('chart');
  const [resolution, setResolution] = useState<string>('1h');
  const [sourceType, setSourceType] = useState<string>('unavailable');
  const [tickers, setTickers] = useState<Ticker[]>([]);
  const [candles, setCandles] = useState<Candle[]>([]);
  const [isLoadingCandles, setIsLoadingCandles] = useState<boolean>(false);
  const [backtestTrades, setBacktestTrades] = useState<BacktestTrade[]>([]);
  const [activeNotifications, setActiveNotifications] = useState<AlertNotification[]>([]);
  const [unreadAlertCount, setUnreadAlertCount] = useState<number>(0);

  // Watchlist Favorites
  const [favorites, setFavorites] = useState<string[]>(() => {
    try {
      const saved = localStorage.getItem('deltapro_favorites');
      return saved ? JSON.parse(saved) : ['BTCUSD', 'ETHUSD', 'SOLUSD'];
    } catch (e) {
      return ['BTCUSD', 'ETHUSD', 'SOLUSD'];
    }
  });

  // Automated Alerts State
  const [alertRules, setAlertRules] = useState<AlertRule[]>(() => {
    try {
      const saved = localStorage.getItem('deltapro_alerts');
      return saved
        ? JSON.parse(saved)
        : [
            {
              id: 'rule-btc-breakout',
              symbol: 'BTCUSD',
              condition: 'crosses_above',
              targetValue: 95500,
              note: 'BTC Psychological Breakout towards 100K',
              soundEnabled: true,
              active: true,
              createdAt: Date.now(),
            },
          ];
    } catch (e) {
      return [];
    }
  });

  const [triggeredHistory, setTriggeredHistory] = useState<AlertNotification[]>([]);
  const [positions, setPositions] = useState<Position[]>([]);
  const [paperBalance, setPaperBalance] = useState<number>(10000);
  const [analysis, setAnalysis] = useState<GeminiMarketAnalysis | null>(null);
  const [isLoadingAnalysis, setIsLoadingAnalysis] = useState<boolean>(false);

  // Sync Indicator Registry to Local Storage
  useEffect(() => {
    try {
      localStorage.setItem('deltapro_v2_indicators', JSON.stringify(indicators));
    } catch (e) {}
  }, [indicators]);

  // Fetch Delta Exchange live tickers periodically
  const fetchTickers = useCallback(async () => {
    try {
      const res = await fetch('/api/delta/tickers');
      const data = await res.json();
      if (data.success && Array.isArray(data.tickers) && data.tickers.length > 0) {
        setTickers(data.tickers);
        setSourceType(data.source || 'delta_live');
      } else {
        setTickers([]);
        setSourceType('unavailable');
      }
    } catch (err) {
      setTickers([]);
      setSourceType('unavailable');
      console.warn('Ticker fetch error:', err);
    }
  }, []);

  // Fetch Delta Candlestick history
  const fetchCandles = useCallback(async () => {
    setIsLoadingCandles(true);
    try {
      const res = await fetch(`/api/delta/candles?symbol=${symbol}&resolution=${resolution}`);
      const data = await res.json();
      if (data.success && Array.isArray(data.candles) && data.candles.length > 0) {
        setCandles(data.candles);
      } else {
        setCandles([]);
      }
    } catch (err) {
      setCandles([]);
      console.warn('Candle fetch error:', err);
    } finally {
      setIsLoadingCandles(false);
    }
  }, [symbol, resolution]);

  useEffect(() => {
    fetchTickers();
    fetchCandles();
    const interval = setInterval(fetchTickers, 3000);
    return () => clearInterval(interval);
  }, [fetchTickers, fetchCandles]);

  // Handle custom file import (JSONL / CSV)
  const handleImportMarketData = (rawText: string) => {
    const lines = rawText.split('\n').filter((l) => l.trim().length > 0);
    const { report, validTrades, validBooks } = validateMarketDataBatch(lines);

    if (validTrades.length > 0) {
      const deltaBars = aggregateTradesIntoDeltaBars(validTrades, 60);
      setMicroData({
        trades: validTrades,
        orderBooks: validBooks.length > 0 ? validBooks : microData.orderBooks,
        deltaBars: deltaBars.length > 0 ? deltaBars : microData.deltaBars,
        rawJsonlLines: lines,
      });
      setQualityReport(report);
      setDatasetId(`IMPORTED-DATASET-${Date.now()}`);
    } else {
      alert(`Import complete with 0 valid trades. Rejection reasons logged in Data Quality tab.`);
      setQualityReport(report);
    }
  };

  // Reset to Clean Synthetic Benchmark
  const handleResetSyntheticData = () => {
    const fresh = generateSyntheticMicrostructureData(240, 94350);
    const { report } = validateMarketDataBatch(fresh.rawJsonlLines);
    setMicroData(fresh);
    setQualityReport(report);
    setDatasetId('BTCUSDT-L2-SYNTH-240M');
  };

  // Register new indicator
  const handleRegisterIndicator = (newInd: IndicatorDefinition) => {
    setIndicators((prev) => [newInd, ...prev]);
  };

  // Update Indicator Status
  const handleUpdateIndicatorStatus = (id: string, status: IndicatorLifecycleStatus) => {
    setIndicators((prev) =>
      prev.map((ind) => (ind.id === id ? { ...ind, status, lastValidatedAt: Date.now() } : ind))
    );
  };

  // Delete Indicator
  const handleDeleteIndicator = (id: string) => {
    setIndicators((prev) => prev.filter((ind) => ind.id !== id));
  };

  const currentTicker = tickers.find((t) => t.symbol === symbol) || tickers[0] || {
    symbol: 'BTCUSD',
    name: 'BTC live feed unavailable',
    mark_price: 0,
    change_24h_percent: 0,
    high_24h: 0,
    low_24h: 0,
    volume_24h: 0,
    funding_rate: 0,
    quotes: { best_bid: 0, best_ask: 0 },
  };

  return (
    <div className="min-h-screen bg-[#07090e] text-slate-100 flex flex-col select-none antialiased">
      {/* Top Workstation Mode Switcher */}
      <div className="bg-[#05070c] border-b border-slate-800/80 px-4 py-1.5 flex items-center justify-between text-xs font-mono">
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1 bg-[#090d16] p-0.5 rounded-xl border border-slate-800">
            <button
              onClick={() => setAppMode('research')}
              className={`flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-sans transition-all ${
                appMode === 'research'
                  ? 'bg-gradient-to-r from-cyan-600 to-blue-600 text-white font-bold shadow-md shadow-cyan-600/30'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <Terminal className="w-3.5 h-3.5" />
              <span>Research Workstation V2</span>
            </button>

            <button
              onClick={() => setAppMode('terminal')}
              className={`flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-sans transition-all ${
                appMode === 'terminal'
                  ? 'bg-gradient-to-r from-purple-600 to-indigo-600 text-white font-bold shadow-md shadow-purple-600/30'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <Smartphone className="w-3.5 h-3.5" />
              <span>Delta Trading Terminal</span>
            </button>
          </div>
        </div>

        <div className="flex items-center gap-3 text-slate-400">
          <span className="hidden sm:inline">
            BTC Price:{' '}
            <span className="text-white font-bold">${currentTicker.mark_price.toLocaleString()}</span>
          </span>
          <span className="flex items-center gap-1 text-[11px] text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/20">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
            ENGINE V2 ACTIVE
          </span>
        </div>
      </div>

      {/* Primary Workstation Router */}
      {appMode === 'research' ? (
        <div className="flex-1 flex flex-col">
          <ResearchHeader
            activeTab={researchTab}
            setActiveTab={setResearchTab}
            datasetId={datasetId}
            setDatasetId={setDatasetId}
            healthScore={qualityReport.healthScore}
            totalRecords={qualityReport.totalRecordsProcessed}
            onOpenDownloadModal={() => setIsDownloadModalOpen(true)}
            symbol={symbol}
            isLive={sourceType === 'delta_live'}
          />

          <main className="flex-1 overflow-y-auto">
            {/* 1. Overview */}
            {researchTab === 'overview' && (
              <OverviewView
                datasetId={datasetId}
                symbol={symbol}
                bars={microData.deltaBars}
                qualityReport={qualityReport}
                indicators={indicators}
                latestExperiment={latestExperiment}
                onNavigateTab={(tab) => setResearchTab(tab)}
              />
            )}

            {/* 2. Data Explorer */}
            {researchTab === 'data_explorer' && (
              <DataExplorerView
                trades={microData.trades}
                orderBooks={microData.orderBooks}
                rawJsonlLines={microData.rawJsonlLines}
                qualityReport={qualityReport}
                onImportData={handleImportMarketData}
                onResetSyntheticData={handleResetSyntheticData}
              />
            )}

            {/* 3. Order Book */}
            {researchTab === 'order_book' && (
              <OrderBookReconstructionView orderBooks={microData.orderBooks} />
            )}

            {/* 4. Delta Analytics */}
            {researchTab === 'delta_analytics' && (
              <DeltaAnalyticsView bars={microData.deltaBars} />
            )}

            {/* 5. Research Lab */}
            {researchTab === 'research_lab' && (
              <ResearchLabView
                bars={microData.deltaBars}
                datasetId={datasetId}
                symbol={symbol}
                onSaveExperimentResult={(res) => setLatestExperiment(res)}
                latestResult={latestExperiment}
              />
            )}

            {/* 6. Indicator Workbench: candle replay and deterministic diagnostics */}
            {researchTab === 'indicator_workbench' && <IndicatorWorkbenchView candles={candles} symbol={symbol} resolution={resolution} />}

            {/* 7. Indicator Builder */}
            {researchTab === 'indicator_builder' && (
              <IndicatorBuilderView onRegisterIndicator={handleRegisterIndicator} />
            )}

            {/* 7. Validation Reports */}
            {researchTab === 'validation_reports' && (
              <ValidationReportsView latestResult={latestExperiment} />
            )}

            {/* 8. Indicator Registry */}
            {researchTab === 'indicator_registry' && (
              <IndicatorRegistryView
                indicators={indicators}
                onUpdateStatus={handleUpdateIndicatorStatus}
                onDeleteIndicator={handleDeleteIndicator}
              />
            )}

            {/* 9. Data Quality */}
            {researchTab === 'data_quality' && (
              <DataQualityView qualityReport={qualityReport} />
            )}

            {/* 10. Settings & Baseline Bridge */}
            {researchTab === 'settings_bridge' && (
              <SettingsAndBridgeView
                bars={microData.deltaBars}
                indicators={indicators}
              />
            )}
          </main>
        </div>
      ) : (
        /* Preserved Live Trading Terminal / Mobile View */
        <AndroidFrame
          activeTab={terminalTab}
          setActiveTab={setTerminalTab}
          activeNotifications={activeNotifications}
          onDismissNotification={(id) =>
            setActiveNotifications((prev) => prev.filter((n) => n.id !== id))
          }
          selectedSymbol={symbol}
          sourceType={sourceType}
          unreadAlertCount={unreadAlertCount}
          onOpenDownloadModal={() => setIsDownloadModalOpen(true)}
        >
          {terminalTab === 'markets' && (
            <Watchlist
              tickers={tickers}
              favorites={favorites}
              onToggleFavorite={(sym) =>
                setFavorites((prev) =>
                  prev.includes(sym) ? prev.filter((s) => s !== sym) : [...prev, sym]
                )
              }
              onSelectSymbol={(sym) => {
                setSymbol(sym);
                setTerminalTab('chart');
              }}
              onOpenAlertModal={(sym) => {
                setSymbol(sym);
                setTerminalTab('alerts');
              }}
              onOpenAlgo={(sym) => {
                setSymbol(sym);
                setTerminalTab('algo');
              }}
              selectedSymbol={symbol}
            />
          )}

          {terminalTab === 'chart' && (
            <div className="flex flex-col h-full overflow-hidden">
              <div className="flex-1 min-h-[380px] w-full">
                <InteractiveChart
                  symbol={symbol}
                  candles={candles}
                  resolution={resolution}
                  setResolution={setResolution}
                  markPrice={currentTicker.mark_price}
                  change24h={currentTicker.change_24h_percent}
                  high24h={currentTicker.high_24h}
                  low24h={currentTicker.low_24h}
                  volume24h={currentTicker.volume_24h}
                  fundingRate={currentTicker.funding_rate}
                  backtestTrades={backtestTrades}
                  onRefresh={fetchCandles}
                  isLoading={isLoadingCandles}
                />
              </div>
              <div className="shrink-0 max-h-[310px] overflow-y-auto">
                <OrderBook
                  markPrice={currentTicker.mark_price}
                  symbol={symbol}
                  bestBid={currentTicker.quotes.best_bid}
                  bestAsk={currentTicker.quotes.best_ask}
                />
              </div>
            </div>
          )}

          {terminalTab === 'alerts' && (
            <AlertsManager
              alertRules={alertRules}
              onAddAlertRule={(r) =>
                setAlertRules((prev) => [{ ...r, id: `rule-${Date.now()}`, createdAt: Date.now() }, ...prev])
              }
              onDeleteAlertRule={(id) => setAlertRules((prev) => prev.filter((r) => r.id !== id))}
              onToggleAlertRule={(id) =>
                setAlertRules((prev) => prev.map((r) => (r.id === id ? { ...r, active: !r.active } : r)))
              }
              triggeredHistory={triggeredHistory}
              onClearHistory={() => setTriggeredHistory([])}
              onTestTriggerAlert={() => {
                playAlertNotificationSound();
                alert('Test alert chime triggered!');
              }}
              tickers={tickers}
              currentSymbol={symbol}
            />
          )}

          {terminalTab === 'dashboard' && (
            <MarketAnalysisDashboard
              currentSymbol={symbol}
              tickers={tickers}
              analysis={analysis}
              isLoadingAnalysis={isLoadingAnalysis}
              onRefreshAnalysis={async () => {
                setIsLoadingAnalysis(true);
                setTimeout(() => setIsLoadingAnalysis(false), 800);
              }}
              markPrice={currentTicker.mark_price}
            />
          )}

          {terminalTab === 'algo' && (
            <AlgoTradingStudio
              currentSymbol={symbol}
              candles={candles}
              markPrice={currentTicker.mark_price}
              onApplyBacktestTradesToChart={(res) => {
                setBacktestTrades(res.trades);
                setTerminalTab('chart');
              }}
              positions={positions}
              onOpenPosition={(pos) =>
                setPositions((prev) => [
                  {
                    ...pos,
                    id: `pos-${Date.now()}`,
                    currentPrice: pos.entryPrice,
                    unrealizedPnl: 0,
                    unrealizedPnlPercent: 0,
                    openedAt: Date.now(),
                  },
                  ...prev,
                ])
              }
              onClosePosition={(id) => setPositions((prev) => prev.filter((p) => p.id !== id))}
              paperBalance={paperBalance}
              tickers={tickers}
            />
          )}
        </AndroidFrame>
      )}

      {/* Download PWA & APK Modal */}
      <DownloadModal
        isOpen={isDownloadModalOpen}
        onClose={() => setIsDownloadModalOpen(false)}
      />
    </div>
  );
}
