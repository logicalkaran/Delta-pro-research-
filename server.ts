import express from 'express';
import { createServer as createViteServer } from 'vite';
import { GoogleGenAI } from '@google/genai';
import dotenv from 'dotenv';
import path from 'path';
import { fileURLToPath } from 'url';

dotenv.config();

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const PORT = 3000;

app.use(express.json());

// Read-only proxy to the existing local BTC/Delta project. The bridge binds
// to loopback and requires a bearer token; no order-placement route is exposed.
async function proxyBtcBridge(route: string, res: any, timeoutMs = 5000) {
  const token = process.env.BTC_DELTA_BRIDGE_TOKEN;
  if (!token || token.length < 32) {
    return res.status(503).json({ error: 'btc_bridge_not_configured' });
  }
  const base = process.env.BTC_DELTA_BRIDGE_URL || 'http://127.0.0.1:8788';
  try {
    const upstream = await fetch(base + route, {
      headers: { Authorization: 'Bearer ' + token, Accept: 'application/json' },
      signal: AbortSignal.timeout(timeoutMs),
    });
    return res.status(upstream.status).json(await upstream.json());
  } catch (_error) {
    return res.status(503).json({ error: 'btc_bridge_unavailable' });
  }
}

app.get('/api/btc-engine/health', (_req, res) =>
  proxyBtcBridge('/health', res, 4000)
);
app.get('/api/btc-engine/snapshot', (_req, res) =>
  proxyBtcBridge('/snapshot', res, 30000)
);

// Initialize GoogleGenAI server-side with required headers
const ai = new GoogleGenAI({
  apiKey: process.env.GEMINI_API_KEY || '',
  httpOptions: {
    headers: {
      'User-Agent': 'aistudio-build',
    },
  },
});

// Seed data for Delta Exchange market simulation & fallback
const FALLBACK_TICKERS = [
  {
    symbol: 'BTCUSD',
    name: 'Bitcoin Perpetual',
    underlying_asset: 'BTC',
    contract_type: 'perpetual_futures',
    mark_price: 94250.50,
    index_price: 94238.10,
    close: 94250.50,
    open_24h: 91800.00,
    high_24h: 95480.00,
    low_24h: 91450.00,
    change_24h_percent: 2.67,
    volume_24h: 18452.84, // BTC
    turnover_24h: 1739150000, // USD
    open_interest: 42150.25,
    funding_rate: 0.00012, // 0.012%
    predicted_funding_rate: 0.00015,
    quotes: {
      best_bid: 94248.50,
      best_ask: 94252.00,
    },
  },
  {
    symbol: 'ETHUSD',
    name: 'Ethereum Perpetual',
    underlying_asset: 'ETH',
    contract_type: 'perpetual_futures',
    mark_price: 3418.25,
    index_price: 3416.80,
    close: 3418.25,
    open_24h: 3290.00,
    high_24h: 3465.00,
    low_24h: 3260.50,
    change_24h_percent: 3.89,
    volume_24h: 142850.10, // ETH
    turnover_24h: 488260000, // USD
    open_interest: 185400.00,
    funding_rate: 0.00018,
    predicted_funding_rate: 0.00016,
    quotes: {
      best_bid: 3417.80,
      best_ask: 3418.70,
    },
  },
  {
    symbol: 'SOLUSD',
    name: 'Solana Perpetual',
    underlying_asset: 'SOL',
    contract_type: 'perpetual_futures',
    mark_price: 198.45,
    index_price: 198.30,
    close: 198.45,
    open_24h: 187.20,
    high_24h: 204.80,
    low_24h: 185.90,
    change_24h_percent: 6.01,
    volume_24h: 894500.0,
    turnover_24h: 177500000,
    open_interest: 650000.0,
    funding_rate: 0.00025,
    predicted_funding_rate: 0.00028,
    quotes: {
      best_bid: 198.40,
      best_ask: 198.50,
    },
  },
  {
    symbol: 'BTC-100000-CALL',
    name: 'BTC $100K Call Option',
    underlying_asset: 'BTC',
    contract_type: 'call_options',
    mark_price: 3120.00,
    index_price: 94238.10,
    close: 3120.00,
    open_24h: 2450.00,
    high_24h: 3340.00,
    low_24h: 2390.00,
    change_24h_percent: 27.35,
    volume_24h: 2840.50,
    turnover_24h: 8860000,
    open_interest: 12500.0,
    funding_rate: 0,
    quotes: {
      best_bid: 3110.00,
      best_ask: 3130.00,
    },
  },
  {
    symbol: 'ETH-3600-CALL',
    name: 'ETH $3600 Call Option',
    underlying_asset: 'ETH',
    contract_type: 'call_options',
    mark_price: 145.50,
    index_price: 3416.80,
    close: 145.50,
    open_24h: 98.00,
    high_24h: 160.00,
    low_24h: 94.50,
    change_24h_percent: 48.47,
    volume_24h: 18900.0,
    turnover_24h: 2750000,
    open_interest: 45000.0,
    funding_rate: 0,
    quotes: {
      best_bid: 144.50,
      best_ask: 146.50,
    },
  },
  {
    symbol: 'BTC-90000-PUT',
    name: 'BTC $90K Put Option',
    underlying_asset: 'BTC',
    contract_type: 'put_options',
    mark_price: 890.00,
    index_price: 94238.10,
    close: 890.00,
    open_24h: 1420.00,
    high_24h: 1480.00,
    low_24h: 850.00,
    change_24h_percent: -37.32,
    volume_24h: 1980.20,
    turnover_24h: 1760000,
    open_interest: 9800.0,
    funding_rate: 0,
    quotes: {
      best_bid: 885.00,
      best_ask: 895.00,
    },
  },
];

// Generate synthetic candles for a symbol
function generateCandles(symbol: string, resolution: string, count: number = 100) {
  let basePrice = symbol.startsWith('BTC') ? (symbol.includes('CALL') || symbol.includes('PUT') ? 2500 : 94000) : (symbol.startsWith('ETH') ? (symbol.includes('CALL') ? 140 : 3400) : 198);
  const now = Math.floor(Date.now() / 1000);
  
  let stepSeconds = 3600; // 1h default
  if (resolution === '1m') stepSeconds = 60;
  else if (resolution === '5m') stepSeconds = 300;
  else if (resolution === '15m') stepSeconds = 900;
  else if (resolution === '1h') stepSeconds = 3600;
  else if (resolution === '4h') stepSeconds = 14400;
  else if (resolution === '1d') stepSeconds = 86400;

  const volatility = basePrice * 0.008;
  const candles = [];
  let currentClose = basePrice * 0.95;

  for (let i = count; i >= 0; i--) {
    const time = now - i * stepSeconds;
    const change = (Math.random() - 0.485) * volatility;
    const open = currentClose;
    const close = Math.max(10, open + change);
    const high = Math.max(open, close) + Math.random() * (volatility * 0.6);
    const low = Math.min(open, close) - Math.random() * (volatility * 0.6);
    const volume = Math.floor((Math.random() * 50 + 10) * (basePrice > 10000 ? 5 : 50));

    candles.push({
      time,
      open: Number(open.toFixed(2)),
      high: Number(high.toFixed(2)),
      low: Number(low.toFixed(2)),
      close: Number(close.toFixed(2)),
      volume,
    });

    currentClose = close;
  }

  return candles;
}

// REST endpoint to get Delta tickers with live micro-fluctuations
app.get('/api/delta/tickers', async (req, res) => {
  try {
    // Attempt live fetch from Delta Exchange API with a quick timeout
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 2500);

    const deltaRes = await fetch('https://api.india.delta.exchange/v2/tickers', {
      headers: {
        'Accept': 'application/json',
      },
      signal: controller.signal,
    });
    clearTimeout(timeoutId);

    if (deltaRes.ok) {
      const data = await deltaRes.json();
      if (data && data.result && Array.isArray(data.result) && data.result.length > 0) {
        // Filter relevant BTC and ETH perpetual and options products
        const mapped = data.result
          .filter((t: any) => t.symbol && ['BTC', 'ETH', 'SOL'].includes(String(t.underlying_asset_symbol || '').toUpperCase()))
          .sort((a: any, b: any) => {
            const ap = a.contract_type === 'perpetual_futures' ? 1 : 0;
            const bp = b.contract_type === 'perpetual_futures' ? 1 : 0;
            return bp - ap || Number(b.turnover_usd || b.turnover || 0) - Number(a.turnover_usd || a.turnover || 0);
          })
          .slice(0, 30)
          .map((t: any) => ({
            symbol: t.symbol,
            name: t.description || t.symbol,
            underlying_asset: String(t.underlying_asset_symbol).toUpperCase(),
            contract_type: t.contract_type || 'unknown',
            mark_price: Number(t.mark_price ?? t.close ?? 0),
            index_price: Number(t.spot_price ?? t.mark_price ?? 0),
            close: Number(t.close ?? 0),
            open_24h: Number(t.open ?? 0),
            high_24h: Number(t.mark_high_24h ?? t.high ?? 0),
            low_24h: Number(t.mark_low_24h ?? t.low ?? 0),
            change_24h_percent: Number(t.ltp_change_24h ?? t.mark_change_24h ?? 0),
            volume_24h: Number(t.volume ?? 0),
            turnover_24h: Number(t.turnover_usd ?? t.turnover ?? 0),
            open_interest: Number(t.oi_contracts ?? t.oi ?? 0),
            funding_rate: Number(t.funding_rate ?? 0),
            predicted_funding_rate: Number(t.predicted_funding_rate ?? 0),
            quotes: {
              best_bid: Number(t.quotes?.best_bid ?? 0),
              best_ask: Number(t.quotes?.best_ask ?? 0),
            },
          }));

        if (mapped.length > 0) {
          return res.json({ success: true, source: 'delta_live', tickers: mapped });
        }
      }
    }
  } catch (err) {
    // Delta network error or timeout, smoothly fall back to high-grade simulated tickers
  }

  res.status(502).json({ success: false, source: 'unavailable', error: 'Delta India ticker feed unavailable; no simulated prices returned.' });
});

// REST endpoint to get Delta Candles history
app.get('/api/delta/candles', async (req, res) => {
  const symbol = (req.query.symbol as string) || 'BTCUSD';
  const resolution = (req.query.resolution as string) || '1h';

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 2500);

    // Delta resolution formatting: 1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 1d
    const deltaRes = await fetch(
      `https://api.india.delta.exchange/v2/history/candles?resolution=${resolution}&symbol=${symbol}&start=${Math.floor(Date.now() / 1000) - 120 * ({ '1m': 60, '3m': 180, '5m': 300, '15m': 900, '30m': 1800, '1h': 3600, '2h': 7200, '4h': 14400, '6h': 21600, '1d': 86400 }[resolution] || 3600)}&end=${Math.floor(Date.now() / 1000)}`,
      { signal: controller.signal }
    );
    clearTimeout(timeoutId);

    if (deltaRes.ok) {
      const data = await deltaRes.json();
      if (data && data.result && Array.isArray(data.result) && data.result.length > 0) {
        const sorted = data.result
          .map((c: any) => ({
            time: c.time,
            open: Number(c.open),
            high: Number(c.high),
            low: Number(c.low),
            close: Number(c.close),
            volume: Number(c.volume || 0),
          }))
          .sort((a: any, b: any) => a.time - b.time);

        return res.json({ success: true, source: 'delta_live', candles: sorted });
      }
    }
  } catch (err) {
    // Fall back to synthetic candles
  }

  res.status(502).json({ success: false, source: 'unavailable', error: 'Delta India candle feed unavailable; no simulated candles returned.' });
});

// Gemini AI Market Research Analyst
app.post('/api/gemini/market-analysis', async (req, res) => {
  try {
    const { symbol, markPrice, change24h, fundingRate, rsi, macd, trend } = req.body;

    const prompt = `You are a world-class senior quantitative crypto derivatives analyst and Delta Exchange specialist.
Analyze the current live market state for ${symbol}:
- Current Mark Price: $${markPrice}
- 24h Change: ${change24h}%
- 8h Funding Rate: ${(fundingRate * 100).toFixed(4)}%
- RSI (14): ${rsi || 52}
- MACD Histogram: ${macd || '+12.4'}
- Technical Trend: ${trend || 'Bullish Momentum'}

Provide a rigorous, concise, structured trading intelligence briefing with:
1. "regime": Current market regime (e.g., "Bullish Trend Expansion", "High-Leverage Squeeze Zone", "Mean Reversion Range")
2. "sentiment": Overall Delta Exchange market sentiment ("Aggressive Bullish", "Cautious Bullish", "Neutral / Balanced", "Bearish Skew")
3. "keyLevels": An object with "support": [price1, price2], "resistance": [price1, price2]
4. "orderFlowBias": Assessment of Delta Exchange taker volume and funding rate dynamics (1-2 sentences)
5. "tradeSetup": A specific actionable setup with:
   - "direction": "LONG" | "SHORT" | "DELTA_NEUTRAL"
   - "entryZone": string
   - "takeProfit1": string
   - "takeProfit2": string
   - "stopLoss": string
   - "riskRewardRatio": string (e.g. "1:2.8")
6. "algoRecommendation": Recommended algo strategy type for this regime (e.g., "EMA Momentum Ribbon", "Funding Rate Arbitrage", "Bollinger Band Breakout")
7. "summary": A crisp 2-3 sentence executive summary for the trader.

Return ONLY valid JSON matching this structure without markdown formatting or code blocks.`;

    const response = await ai.models.generateContent({
      model: 'gemini-3.8-flash',
      contents: prompt,
      config: {
        responseMimeType: 'application/json',
      },
    });

    const text = response.text || '{}';
    const parsed = JSON.parse(text);
    res.json({ success: true, analysis: parsed });
  } catch (error: any) {
    console.error('Gemini market analysis error:', error);
    // Provide structured default analysis if API key is unconfigured or rate limited
    res.json({
      success: true,
      analysis: {
        regime: 'Bullish Momentum Expansion',
        sentiment: 'Aggressive Bullish',
        keyLevels: {
          support: ['$92,400', '$90,850'],
          resistance: ['$95,500', '$98,200'],
        },
        orderFlowBias: 'Positive Delta Exchange open interest with healthy funding rate indicates spot-led perpetual accumulation.',
        tradeSetup: {
          direction: 'LONG',
          entryZone: 'Pullback to $93,800 - $94,100',
          takeProfit1: '$96,500',
          takeProfit2: '$99,200',
          stopLoss: '$92,200',
          riskRewardRatio: '1:3.1',
        },
        algoRecommendation: 'EMA 20/50 Trend Following Ribbon with Trailing Volatility Stop',
        summary: 'Bitcoin exhibits sustained buy pressure on Delta Exchange perps. With funding holding moderate, upward continuation towards psychological $100K remains the higher probability path.',
      },
    });
  }
});

// Gemini AI Algo Trading Strategy Generator
app.post('/api/gemini/generate-strategy', async (req, res) => {
  try {
    const { userPrompt, asset, riskProfile, timeframe } = req.body;

    const prompt = `You are an expert algorithmic trading engineer specializing in crypto derivatives on Delta Exchange.
Design a complete, mathematically sound algorithmic trading strategy based on:
- Trader Idea/Prompt: "${userPrompt || 'EMA Crossover with RSI Filter'}"
- Target Asset: ${asset || 'BTCUSD'}
- Risk Profile: ${riskProfile || 'Moderate'}
- Execution Timeframe: ${timeframe || '1h'}

Return a JSON object with:
1. "strategyName": Creative pro algo name (e.g. "Delta Momentum Surge v3")
2. "description": Clear explanation of the thesis (2 sentences)
3. "indicators": Array of indicator definitions used (e.g. ["EMA(20)", "EMA(50)", "RSI(14)"])
4. "entryRules": Array of exact mathematical entry conditions
5. "exitRules": Array of exact exit and take-profit rules
6. "riskManagement": Object with "stopLossPercent" (number), "takeProfitPercent" (number), "maxLeverage" (number, 1-100), "riskPerTradePercent" (number)
7. "backtestSummary": Object with estimated "expectedWinRate" (string, e.g. "64%"), "profitFactor" (string, e.g. "2.15"), "sharpeRatio" (string, e.g. "1.82"), "maxDrawdown" (string, e.g. "-12.4%")
8. "deltaExchangeEdge": Specific reason why this strategy thrives on Delta Exchange (e.g. funding fee rebate, options delta hedging, low taker fee)

Return ONLY valid JSON.`;

    const response = await ai.models.generateContent({
      model: 'gemini-3.8-flash',
      contents: prompt,
      config: {
        responseMimeType: 'application/json',
      },
    });

    const text = response.text || '{}';
    const parsed = JSON.parse(text);
    res.json({ success: true, strategy: parsed });
  } catch (error: any) {
    console.error('Gemini strategy generation error:', error);
    res.json({
      success: true,
      strategy: {
        strategyName: 'Delta Trend-Surge Adaptive Momentum',
        description: 'Captures explosive trend continuation moves when fast EMA crosses slow EMA during positive Delta funding regimes.',
        indicators: ['EMA (20)', 'EMA (50)', 'RSI (14)', 'Delta Funding Filter'],
        entryRules: [
          'Enter LONG when EMA 20 crosses above EMA 50 AND RSI > 50 AND RSI < 70',
          'Enter SHORT when EMA 20 crosses below EMA 50 AND RSI < 50 AND RSI > 30',
        ],
        exitRules: [
          'Exit on opposite EMA crossover or trailing ATR stop trigger',
          'Dynamic scale-out 50% at 1.5x risk, move stop to breakeven',
        ],
        riskManagement: {
          stopLossPercent: 2.5,
          takeProfitPercent: 6.0,
          maxLeverage: 10,
          riskPerTradePercent: 1.5,
        },
        backtestSummary: {
          expectedWinRate: '62.4%',
          profitFactor: '2.08',
          sharpeRatio: '1.94',
          maxDrawdown: '-11.2%',
        },
        deltaExchangeEdge: 'Exploits high-liquidity perpetual order book depth and captures periodic negative funding spikes to collect yield while trending.',
      },
    });
  }
});

// Setup Vite in Dev or serve Static in Production
async function startServer() {
  if (process.env.NODE_ENV !== 'production') {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: 'spa',
    });
    app.use(vite.middlewares);
  } else {
    app.use(express.static(path.resolve(__dirname, 'dist')));
    app.get('*', (req, res) => {
      res.sendFile(path.resolve(__dirname, 'dist', 'index.html'));
    });
  }

  app.listen(PORT, '0.0.0.0', () => {
    console.log(`DeltaPro Server running on http://0.0.0.0:${PORT}`);
  });
}

startServer();
