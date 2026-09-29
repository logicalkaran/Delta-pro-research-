import React, { useRef, useEffect, useState, useMemo, useCallback } from 'react';
import {
  Maximize2,
  TrendingUp,
  Activity,
  Layers,
  ChevronDown,
  Eye,
  EyeOff,
  Crosshair,
  RefreshCw,
  Compass,
} from 'lucide-react';
import { Candle, BacktestTrade } from '../types/crypto';
import {
  calculateEMA,
  calculateBollingerBands,
  calculateRSI,
  calculateHeikinAshi,
} from '../utils/indicators';

interface InteractiveChartProps {
  symbol: string;
  candles: Candle[];
  resolution: string;
  setResolution: (res: string) => void;
  markPrice: number;
  change24h: number;
  high24h: number;
  low24h: number;
  volume24h: number;
  fundingRate: number;
  backtestTrades?: BacktestTrade[];
  onRefresh?: () => void;
  isLoading?: boolean;
}

export const InteractiveChart: React.FC<InteractiveChartProps> = ({
  symbol,
  candles,
  resolution,
  setResolution,
  markPrice,
  change24h,
  high24h,
  low24h,
  volume24h,
  fundingRate,
  backtestTrades = [],
  onRefresh,
  isLoading,
}) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  // Chart configuration state
  const [chartType, setChartType] = useState<'candles' | 'line' | 'heikin'>('candles');
  const [showEMA20, setShowEMA20] = useState(true);
  const [showEMA50, setShowEMA50] = useState(true);
  const [showBB, setShowBB] = useState(false);
  const [showRSI, setShowRSI] = useState(true);
  const [showTrades, setShowTrades] = useState(true);
  const [crosshairInfo, setCrosshairInfo] = useState<{
    candle: Candle;
    x: number;
    y: number;
    price: number;
  } | null>(null);

  // Timeframes supported by Delta Exchange
  const timeframes = ['1m', '5m', '15m', '1h', '4h', '1d'];

  // Process data with selected chart type
  const processedCandles = useMemo(() => {
    if (chartType === 'heikin') {
      return calculateHeikinAshi(candles);
    }
    return candles;
  }, [candles, chartType]);

  const closes = useMemo(() => processedCandles.map((c) => c.close), [processedCandles]);
  const ema20 = useMemo(() => calculateEMA(closes, 20), [closes]);
  const ema50 = useMemo(() => calculateEMA(closes, 50), [closes]);
  const bb = useMemo(() => calculateBollingerBands(closes, 20, 2), [closes]);
  const rsi = useMemo(() => calculateRSI(closes, 14), [closes]);

  // Main Canvas render function
  const renderChart = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas || processedCandles.length === 0) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Support High-DPI displays
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    const width = rect.width;
    const height = rect.height;

    canvas.width = width * dpr;
    canvas.height = height * dpr;
    ctx.scale(dpr, dpr);

    // Clear background
    ctx.fillStyle = '#090d16';
    ctx.fillRect(0, 0, width, height);

    // Layout partitioning: Main chart (72%) + RSI Sub-panel (28% if enabled)
    const rightPriceAxisWidth = 65;
    const bottomTimeAxisHeight = 22;
    const subChartHeight = showRSI ? Math.floor(height * 0.24) : 0;
    const mainChartHeight = height - bottomTimeAxisHeight - subChartHeight;
    const chartWidth = width - rightPriceAxisWidth;

    const dataCount = processedCandles.length;
    if (dataCount === 0) return;

    // Dynamic price scale bounds
    let minPrice = Infinity;
    let maxPrice = -Infinity;
    let maxVol = 0;

    for (let i = 0; i < dataCount; i++) {
      const c = processedCandles[i];
      if (c.low < minPrice) minPrice = c.low;
      if (c.high > maxPrice) maxPrice = c.high;
      if (c.volume > maxVol) maxVol = c.volume;

      if (showBB && bb.upper[i] && bb.lower[i]) {
        if (bb.upper[i]! > maxPrice) maxPrice = bb.upper[i]!;
        if (bb.lower[i]! < minPrice) minPrice = bb.lower[i]!;
      }
    }

    if (minPrice === maxPrice) {
      minPrice *= 0.98;
      maxPrice *= 1.02;
    }
    const pricePadding = (maxPrice - minPrice) * 0.08;
    minPrice -= pricePadding;
    maxPrice += pricePadding;
    const priceRange = maxPrice - minPrice;

    // Helper coordinates
    const getX = (index: number) => {
      return (index / (dataCount - 1 || 1)) * chartWidth;
    };
    const getY = (price: number) => {
      return mainChartHeight - ((price - minPrice) / priceRange) * mainChartHeight;
    };

    // Draw Subtle Grid Lines
    ctx.strokeStyle = '#172033';
    ctx.lineWidth = 1;
    ctx.setLineDash([3, 4]);

    const priceSteps = 6;
    for (let i = 0; i <= priceSteps; i++) {
      const p = minPrice + (priceRange / priceSteps) * i;
      const y = getY(p);
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(chartWidth, y);
      ctx.stroke();

      // Price text labels on right axis
      ctx.fillStyle = '#64748b';
      ctx.font = '10px JetBrains Mono, monospace';
      ctx.textAlign = 'left';
      ctx.fillText(p >= 1000 ? p.toFixed(1) : p.toFixed(2), chartWidth + 6, y + 3);
    }
    ctx.setLineDash([]);

    // Draw Volume Bars on background
    const volMaxHeight = mainChartHeight * 0.22;
    for (let i = 0; i < dataCount; i++) {
      const c = processedCandles[i];
      const x = getX(i);
      const barW = Math.max(1.8, (chartWidth / dataCount) * 0.65);
      const barH = maxVol > 0 ? (c.volume / maxVol) * volMaxHeight : 4;
      const y = mainChartHeight - barH;

      ctx.fillStyle = c.close >= c.open ? 'rgba(34, 197, 94, 0.18)' : 'rgba(239, 68, 68, 0.18)';
      ctx.fillRect(x - barW / 2, y, barW, barH);
    }

    // Draw Bollinger Bands if enabled
    if (showBB) {
      // Shaded channel
      ctx.beginPath();
      let started = false;
      for (let i = 0; i < dataCount; i++) {
        if (bb.upper[i] !== null) {
          const x = getX(i);
          const y = getY(bb.upper[i]!);
          if (!started) {
            ctx.moveTo(x, y);
            started = true;
          } else {
            ctx.lineTo(x, y);
          }
        }
      }
      for (let i = dataCount - 1; i >= 0; i--) {
        if (bb.lower[i] !== null) {
          const x = getX(i);
          const y = getY(bb.lower[i]!);
          ctx.lineTo(x, y);
        }
      }
      ctx.closePath();
      ctx.fillStyle = 'rgba(56, 189, 248, 0.05)';
      ctx.fill();

      // Upper and lower boundary lines
      ctx.strokeStyle = 'rgba(56, 189, 248, 0.4)';
      ctx.lineWidth = 1;
      ctx.beginPath();
      for (let i = 0; i < dataCount; i++) {
        if (bb.upper[i] !== null) {
          const x = getX(i);
          const y = getY(bb.upper[i]!);
          if (i === 19) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
      }
      ctx.stroke();

      ctx.beginPath();
      for (let i = 0; i < dataCount; i++) {
        if (bb.lower[i] !== null) {
          const x = getX(i);
          const y = getY(bb.lower[i]!);
          if (i === 19) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
      }
      ctx.stroke();
    }

    // Draw EMA 20 (Cyan)
    if (showEMA20) {
      ctx.strokeStyle = '#06b6d4';
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      let started = false;
      for (let i = 0; i < dataCount; i++) {
        if (ema20[i] !== null) {
          const x = getX(i);
          const y = getY(ema20[i]!);
          if (!started) {
            ctx.moveTo(x, y);
            started = true;
          } else {
            ctx.lineTo(x, y);
          }
        }
      }
      ctx.stroke();
    }

    // Draw EMA 50 (Purple)
    if (showEMA50) {
      ctx.strokeStyle = '#a855f7';
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      let started = false;
      for (let i = 0; i < dataCount; i++) {
        if (ema50[i] !== null) {
          const x = getX(i);
          const y = getY(ema50[i]!);
          if (!started) {
            ctx.moveTo(x, y);
            started = true;
          } else {
            ctx.lineTo(x, y);
          }
        }
      }
      ctx.stroke();
    }

    // Draw Candlesticks or Line
    const candleWidth = Math.max(2, (chartWidth / dataCount) * 0.75);

    if (chartType === 'line') {
      // Area / Line chart
      ctx.beginPath();
      ctx.moveTo(getX(0), getY(processedCandles[0].close));
      for (let i = 1; i < dataCount; i++) {
        ctx.lineTo(getX(i), getY(processedCandles[i].close));
      }
      ctx.strokeStyle = '#38bdf8';
      ctx.lineWidth = 2;
      ctx.stroke();

      // Gradient under line
      ctx.lineTo(getX(dataCount - 1), mainChartHeight);
      ctx.lineTo(getX(0), mainChartHeight);
      ctx.closePath();
      const grad = ctx.createLinearGradient(0, 0, 0, mainChartHeight);
      grad.addColorStop(0, 'rgba(56, 189, 248, 0.25)');
      grad.addColorStop(1, 'rgba(56, 189, 248, 0.0)');
      ctx.fillStyle = grad;
      ctx.fill();
    } else {
      // Candlesticks (Standard or Heikin-Ashi)
      for (let i = 0; i < dataCount; i++) {
        const c = processedCandles[i];
        const x = getX(i);
        const openY = getY(c.open);
        const closeY = getY(c.close);
        const highY = getY(c.high);
        const lowY = getY(c.low);

        const isBullish = c.close >= c.open;
        const color = isBullish ? '#22c55e' : '#ef4444';

        // Draw Wick
        ctx.strokeStyle = color;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(x, highY);
        ctx.lineTo(x, lowY);
        ctx.stroke();

        // Draw Body
        ctx.fillStyle = color;
        const bodyTop = Math.min(openY, closeY);
        const bodyHeight = Math.max(1.5, Math.abs(closeY - openY));
        ctx.fillRect(x - candleWidth / 2, bodyTop, candleWidth, bodyHeight);
      }
    }

    // Trade Markers from Backtested Algo or Paper Positions
    if (showTrades && backtestTrades.length > 0) {
      const candleTimes = processedCandles.map((c) => c.time);
      for (const t of backtestTrades) {
        // Find closest candle index
        let closestIdx = -1;
        let minDiff = Infinity;
        for (let i = 0; i < candleTimes.length; i++) {
          const diff = Math.abs(candleTimes[i] - t.entryTime);
          if (diff < minDiff) {
            minDiff = diff;
            closestIdx = i;
          }
        }

        if (closestIdx !== -1) {
          const x = getX(closestIdx);
          const y = getY(t.entryPrice);
          const isBuy = t.type === 'BUY';

          ctx.fillStyle = isBuy ? '#10b981' : '#f43f5e';
          ctx.beginPath();
          if (isBuy) {
            // Triangle pointing up
            ctx.moveTo(x, y + 14);
            ctx.lineTo(x - 5, y + 24);
            ctx.lineTo(x + 5, y + 24);
          } else {
            // Triangle pointing down
            ctx.moveTo(x, y - 14);
            ctx.lineTo(x - 5, y - 24);
            ctx.lineTo(x + 5, y - 24);
          }
          ctx.closePath();
          ctx.fill();

          // Small tag
          ctx.font = '8px JetBrains Mono, monospace';
          ctx.fillStyle = '#ffffff';
          ctx.textAlign = 'center';
          ctx.fillText(isBuy ? 'L' : 'S', x, isBuy ? y + 21 : y - 17);
        }
      }
    }

    // Current Price Indicator Tag on Right Axis
    const currentPriceY = getY(markPrice);
    if (currentPriceY >= 0 && currentPriceY <= mainChartHeight) {
      // Horizontal dashed line
      ctx.strokeStyle = '#06b6d4';
      ctx.setLineDash([4, 4]);
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(0, currentPriceY);
      ctx.lineTo(chartWidth, currentPriceY);
      ctx.stroke();
      ctx.setLineDash([]);

      // Badge on right
      ctx.fillStyle = '#0891b2';
      ctx.fillRect(chartWidth + 1, currentPriceY - 9, rightPriceAxisWidth - 2, 18);
      ctx.fillStyle = '#ffffff';
      ctx.font = 'bold 10px JetBrains Mono, monospace';
      ctx.textAlign = 'left';
      ctx.fillText(markPrice >= 1000 ? markPrice.toFixed(1) : markPrice.toFixed(2), chartWidth + 5, currentPriceY + 3.5);
    }

    // Sub-Chart: RSI (14)
    if (showRSI) {
      const subTop = mainChartHeight;
      const subHeight = subChartHeight - bottomTimeAxisHeight;

      // Sub-chart separator
      ctx.strokeStyle = '#1e293b';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(0, subTop);
      ctx.lineTo(width, subTop);
      ctx.stroke();

      // Background
      ctx.fillStyle = '#080c14';
      ctx.fillRect(0, subTop, chartWidth, subHeight);

      // Overbought 70 and Oversold 30 threshold lines
      const getY_RSI = (val: number) => subTop + subHeight - (val / 100) * subHeight;

      ctx.strokeStyle = '#334155';
      ctx.setLineDash([2, 4]);
      ctx.lineWidth = 1;

      // 70 line
      ctx.beginPath();
      ctx.moveTo(0, getY_RSI(70));
      ctx.lineTo(chartWidth, getY_RSI(70));
      ctx.stroke();

      // 30 line
      ctx.beginPath();
      ctx.moveTo(0, getY_RSI(30));
      ctx.lineTo(chartWidth, getY_RSI(30));
      ctx.stroke();
      ctx.setLineDash([]);

      // Label
      ctx.fillStyle = '#94a3b8';
      ctx.font = '9px JetBrains Mono, monospace';
      ctx.textAlign = 'left';
      ctx.fillText('RSI (14)', 8, subTop + 14);

      const latestRSI = rsi[rsi.length - 1];
      if (latestRSI !== null && latestRSI !== undefined) {
        ctx.fillStyle = latestRSI > 70 ? '#ef4444' : latestRSI < 30 ? '#22c55e' : '#38bdf8';
        ctx.fillText(`${latestRSI.toFixed(1)}`, 54, subTop + 14);
      }

      ctx.fillText('70', chartWidth + 6, getY_RSI(70) + 3);
      ctx.fillText('30', chartWidth + 6, getY_RSI(30) + 3);

      // Draw RSI line
      ctx.strokeStyle = '#38bdf8';
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      let started = false;
      for (let i = 0; i < dataCount; i++) {
        if (rsi[i] !== null) {
          const x = getX(i);
          const y = getY_RSI(rsi[i]!);
          if (!started) {
            ctx.moveTo(x, y);
            started = true;
          } else {
            ctx.lineTo(x, y);
          }
        }
      }
      ctx.stroke();
    }

    // Time Axis Labels (Bottom)
    const timeAxisY = height - 6;
    ctx.fillStyle = '#64748b';
    ctx.font = '9px JetBrains Mono, monospace';
    ctx.textAlign = 'center';

    const timeInterval = Math.max(1, Math.floor(dataCount / 5));
    for (let i = 0; i < dataCount; i += timeInterval) {
      const c = processedCandles[i];
      const d = new Date(c.time * 1000);
      const timeStr = `${d.getHours().toString().padStart(2, '0')}:${d
        .getMinutes()
        .toString()
        .padStart(2, '0')}`;
      ctx.fillText(timeStr, getX(i), timeAxisY);
    }

    // Crosshair rendering
    if (crosshairInfo) {
      const { x, y, candle, price } = crosshairInfo;

      ctx.strokeStyle = '#94a3b8';
      ctx.setLineDash([3, 3]);
      ctx.lineWidth = 1;

      // Vertical line
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, height - bottomTimeAxisHeight);
      ctx.stroke();

      // Horizontal line (only in main chart if y <= mainChartHeight)
      if (y <= mainChartHeight) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(chartWidth, y);
        ctx.stroke();

        // Price pill
        ctx.fillStyle = '#1e293b';
        ctx.fillRect(chartWidth + 1, y - 9, rightPriceAxisWidth - 2, 18);
        ctx.fillStyle = '#f8fafc';
        ctx.textAlign = 'left';
        ctx.font = '10px JetBrains Mono, monospace';
        ctx.fillText(price >= 1000 ? price.toFixed(1) : price.toFixed(2), chartWidth + 5, y + 3.5);
      }
      ctx.setLineDash([]);
    }
  }, [
    processedCandles,
    chartType,
    showEMA20,
    showEMA50,
    showBB,
    showRSI,
    showTrades,
    crosshairInfo,
    ema20,
    ema50,
    bb,
    rsi,
    markPrice,
    backtestTrades,
  ]);

  // Handle crosshair mouse/touch move
  const handlePointerMove = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas || processedCandles.length === 0) return;

    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    const rightPriceAxisWidth = 65;
    const chartWidth = rect.width - rightPriceAxisWidth;

    if (x < 0 || x > chartWidth) {
      setCrosshairInfo(null);
      return;
    }

    const dataCount = processedCandles.length;
    const ratio = Math.max(0, Math.min(1, x / chartWidth));
    const index = Math.round(ratio * (dataCount - 1));
    const candle = processedCandles[index];

    // Compute price at y
    let minPrice = Infinity;
    let maxPrice = -Infinity;
    for (const c of processedCandles) {
      if (c.low < minPrice) minPrice = c.low;
      if (c.high > maxPrice) maxPrice = c.high;
    }
    const padding = (maxPrice - minPrice) * 0.08;
    minPrice -= padding;
    maxPrice += padding;
    const subHeight = showRSI ? Math.floor(rect.height * 0.24) : 0;
    const mainChartHeight = rect.height - 22 - subHeight;
    const priceRange = maxPrice - minPrice;
    const price = maxPrice - (y / mainChartHeight) * priceRange;

    setCrosshairInfo({
      candle,
      x: (index / (dataCount - 1 || 1)) * chartWidth,
      y,
      price,
    });
  };

  const handlePointerLeave = () => {
    setCrosshairInfo(null);
  };

  // Redraw when container dimensions or dependencies change
  useEffect(() => {
    renderChart();
    const handleResize = () => renderChart();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [renderChart]);

  const activeCandle = crosshairInfo ? crosshairInfo.candle : processedCandles[processedCandles.length - 1];

  return (
    <div className="flex flex-col w-full h-full bg-[#080c14] select-none text-slate-200">
      {/* Top Ticker Summary Bar */}
      <div className="px-3 py-2 bg-[#0d121f] border-b border-slate-800/80 flex flex-wrap items-center justify-between gap-2 shrink-0">
        <div className="flex items-center gap-2">
          <div>
            <div className="flex items-center gap-1.5">
              <span className="font-extrabold text-sm tracking-wide text-white font-mono">
                {symbol}
              </span>
              <span className="text-[10px] px-1 py-0.2 rounded font-mono bg-cyan-950 text-cyan-400 border border-cyan-800/60">
                PERP
              </span>
              <span className="text-[10px] text-slate-400 font-mono">Delta Exchange</span>
            </div>
            <div className="flex items-baseline gap-2 mt-0.5">
              <span
                className={`font-mono font-bold text-lg leading-none ${
                  change24h >= 0 ? 'text-emerald-400' : 'text-rose-400'
                }`}
              >
                ${markPrice.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </span>
              <span
                className={`text-xs font-mono font-semibold px-1.5 py-0.5 rounded ${
                  change24h >= 0
                    ? 'bg-emerald-500/15 text-emerald-400'
                    : 'bg-rose-500/15 text-rose-400'
                }`}
              >
                {change24h >= 0 ? '+' : ''}
                {change24h.toFixed(2)}%
              </span>
            </div>
          </div>
        </div>

        {/* Quick Market Stats */}
        <div className="flex items-center gap-3 text-[11px] font-mono text-slate-300">
          <div>
            <span className="text-slate-500 text-[10px] block">24h High/Low</span>
            <span>
              ${high24h.toLocaleString()} / ${low24h.toLocaleString()}
            </span>
          </div>
          <div>
            <span className="text-slate-500 text-[10px] block">8h Funding</span>
            <span className={fundingRate >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
              {(fundingRate * 100).toFixed(4)}%
            </span>
          </div>
          {onRefresh && (
            <button
              onClick={onRefresh}
              className={`p-1.5 rounded-lg bg-slate-800/80 hover:bg-slate-700 text-slate-300 transition-all ${
                isLoading ? 'animate-spin text-cyan-400' : ''
              }`}
              title="Refresh Delta Exchange data"
            >
              <RefreshCw className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* Interactive Toolbars: Timeframes & Indicators */}
      <div className="px-3 py-1.5 bg-[#0a0e18] border-b border-slate-800/60 flex items-center justify-between text-xs overflow-x-auto gap-2 shrink-0">
        {/* Timeframe Buttons */}
        <div className="flex items-center gap-1">
          {timeframes.map((tf) => (
            <button
              key={tf}
              onClick={() => setResolution(tf)}
              className={`px-2 py-0.8 rounded text-[11px] font-mono font-medium transition-all ${
                resolution === tf
                  ? 'bg-cyan-500 text-slate-950 font-bold shadow-sm shadow-cyan-500/40'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
              }`}
            >
              {tf}
            </button>
          ))}
        </div>

        {/* Chart Style & Indicators Toggles */}
        <div className="flex items-center gap-1.5 text-[11px]">
          {/* Chart Type Dropdown/Toggle */}
          <div className="flex bg-slate-800/70 p-0.5 rounded-lg border border-slate-700/60">
            <button
              onClick={() => setChartType('candles')}
              className={`px-1.5 py-0.5 rounded text-[10px] ${
                chartType === 'candles' ? 'bg-cyan-600 text-white font-semibold' : 'text-slate-400'
              }`}
            >
              Candle
            </button>
            <button
              onClick={() => setChartType('heikin')}
              className={`px-1.5 py-0.5 rounded text-[10px] ${
                chartType === 'heikin' ? 'bg-cyan-600 text-white font-semibold' : 'text-slate-400'
              }`}
            >
              Heikin
            </button>
            <button
              onClick={() => setChartType('line')}
              className={`px-1.5 py-0.5 rounded text-[10px] ${
                chartType === 'line' ? 'bg-cyan-600 text-white font-semibold' : 'text-slate-400'
              }`}
            >
              Line
            </button>
          </div>

          {/* Indicator Pills */}
          <button
            onClick={() => setShowEMA20(!showEMA20)}
            className={`px-1.5 py-0.5 rounded text-[10px] font-mono border transition-all ${
              showEMA20
                ? 'bg-cyan-500/20 text-cyan-300 border-cyan-500/50'
                : 'bg-transparent text-slate-500 border-slate-800'
            }`}
          >
            EMA20
          </button>
          <button
            onClick={() => setShowEMA50(!showEMA50)}
            className={`px-1.5 py-0.5 rounded text-[10px] font-mono border transition-all ${
              showEMA50
                ? 'bg-purple-500/20 text-purple-300 border-purple-500/50'
                : 'bg-transparent text-slate-500 border-slate-800'
            }`}
          >
            EMA50
          </button>
          <button
            onClick={() => setShowBB(!showBB)}
            className={`px-1.5 py-0.5 rounded text-[10px] font-mono border transition-all ${
              showBB
                ? 'bg-sky-500/20 text-sky-300 border-sky-500/50'
                : 'bg-transparent text-slate-500 border-slate-800'
            }`}
          >
            BB(20)
          </button>
          <button
            onClick={() => setShowRSI(!showRSI)}
            className={`px-1.5 py-0.5 rounded text-[10px] font-mono border transition-all ${
              showRSI
                ? 'bg-amber-500/20 text-amber-300 border-amber-500/50'
                : 'bg-transparent text-slate-500 border-slate-800'
            }`}
          >
            RSI
          </button>
          {backtestTrades.length > 0 && (
            <button
              onClick={() => setShowTrades(!showTrades)}
              className={`px-1.5 py-0.5 rounded text-[10px] font-mono border transition-all ${
                showTrades
                  ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/50'
                  : 'bg-transparent text-slate-500 border-slate-800'
              }`}
            >
              Algo({backtestTrades.length})
            </button>
          )}
        </div>
      </div>

      {/* OHLCV Crosshair Readout Bar */}
      {activeCandle && (
        <div className="px-3 py-1 bg-[#090d16] flex items-center gap-3 text-[10px] font-mono text-slate-400 overflow-x-auto border-b border-slate-800/40 shrink-0">
          <span className="text-slate-300">
            {new Date(activeCandle.time * 1000).toLocaleString([], {
              month: 'short',
              day: 'numeric',
              hour: '2-digit',
              minute: '2-digit',
            })}
          </span>
          <span>
            O: <span className="text-slate-200">${activeCandle.open.toFixed(2)}</span>
          </span>
          <span>
            H: <span className="text-slate-200">${activeCandle.high.toFixed(2)}</span>
          </span>
          <span>
            L: <span className="text-slate-200">${activeCandle.low.toFixed(2)}</span>
          </span>
          <span>
            C:{' '}
            <span
              className={
                activeCandle.close >= activeCandle.open ? 'text-emerald-400' : 'text-rose-400'
              }
            >
              ${activeCandle.close.toFixed(2)}
            </span>
          </span>
          <span>
            Vol: <span className="text-slate-200">{activeCandle.volume.toLocaleString()}</span>
          </span>
        </div>
      )}

      {/* Interactive Canvas Canvas Area */}
      <div ref={containerRef} className="flex-1 w-full relative min-h-[280px]">
        <canvas
          ref={canvasRef}
          onPointerMove={handlePointerMove}
          onPointerLeave={handlePointerLeave}
          className="w-full h-full cursor-crosshair touch-none block"
        />

        {/* Live Loading Overlay */}
        {isLoading && (
          <div className="absolute inset-0 bg-slate-950/40 backdrop-blur-[1px] flex items-center justify-center pointer-events-none">
            <div className="flex items-center gap-2 px-3 py-1.5 bg-slate-900 border border-cyan-500/40 rounded-full text-xs font-mono text-cyan-300 shadow-xl">
              <RefreshCw className="w-3.5 h-3.5 animate-spin text-cyan-400" />
              <span>Streaming Delta Candles...</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
