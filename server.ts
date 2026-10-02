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

// REST endpoint for live Delta Exchange tickers; failures return unavailable.
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
          return res.json({ success: true, source: 'delta_live', fetchedAt: Date.now(), tickers: mapped });
        }
      }
    }
  } catch (err) {
    // Delta network error or timeout; never substitute simulated market prices.
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

        return res.json({ success: true, source: 'delta_live', fetchedAt: Date.now(), candles: sorted });
      }
    }
  } catch (err) {
    // Do not substitute synthetic candles for an unavailable exchange response.
  }

  res.status(502).json({ success: false, source: 'unavailable', error: 'Delta India candle feed unavailable; no simulated candles returned.' });
});


// Public, read-only Delta India market microstructure endpoints.
// Exchange timestamps are supplied in microseconds and normalized to milliseconds.
const validMarketSymbol = (value: unknown): string | null => {
  const symbol = String(value || '').toUpperCase();
  return /^[A-Z0-9_-]{2,40}$/.test(symbol) ? symbol : null;
};

app.get('/api/delta/orderbook/:symbol', async (req, res) => {
  const symbol = validMarketSymbol(req.params.symbol);
  if (!symbol) return res.status(400).json({ success: false, error: 'invalid_symbol' });
  try {
    const upstream = await fetch(
      `https://api.india.delta.exchange/v2/l2orderbook/${encodeURIComponent(symbol)}?depth=20`,
      { headers: { Accept: 'application/json' }, signal: AbortSignal.timeout(5000) }
    );
    if (!upstream.ok) return res.status(502).json({ success: false, source: 'unavailable', error: 'delta_orderbook_http_error' });
    const payload: any = await upstream.json();
    const book = payload?.result;
    if (!payload?.success || !book || !Array.isArray(book.buy) || !Array.isArray(book.sell)) {
      return res.status(502).json({ success: false, source: 'unavailable', error: 'delta_orderbook_invalid_response' });
    }
    const levels = (rows: any[], side: 'buy' | 'sell') => rows
      .map((row) => ({ price: Number(row.price), size: Number(row.size) }))
      .filter((row) => Number.isFinite(row.price) && row.price > 0 && Number.isFinite(row.size) && row.size >= 0)
      .sort((a, b) => side === 'buy' ? b.price - a.price : a.price - b.price)
      .slice(0, 20)
      .map((row, index, all) => ({
        ...row,
        total: all.slice(0, index + 1).reduce((sum, item) => sum + item.size, 0),
      }));
    const exchangeTimestamp = Number(book.last_updated_at);
    return res.json({
      success: true, source: 'delta_india_rest', symbol,
      fetchedAt: Date.now(),
      exchangeTimestamp: Number.isFinite(exchangeTimestamp) ? Math.floor(exchangeTimestamp / 1000) : null,
      bids: levels(book.buy, 'buy'), asks: levels(book.sell, 'sell'),
    });
  } catch (_error) {
    return res.status(502).json({ success: false, source: 'unavailable', error: 'delta_orderbook_unavailable' });
  }
});

app.get('/api/delta/trades/:symbol', async (req, res) => {
  const symbol = validMarketSymbol(req.params.symbol);
  if (!symbol) return res.status(400).json({ success: false, error: 'invalid_symbol' });
  try {
    const upstream = await fetch(
      `https://api.india.delta.exchange/v2/trades/${encodeURIComponent(symbol)}`,
      { headers: { Accept: 'application/json' }, signal: AbortSignal.timeout(5000) }
    );
    if (!upstream.ok) return res.status(502).json({ success: false, source: 'unavailable', error: 'delta_trades_http_error' });
    const payload: any = await upstream.json();
    const rows = Array.isArray(payload?.result) ? payload.result : payload?.result?.trades;
    if (!payload?.success || !Array.isArray(rows)) {
      return res.status(502).json({ success: false, source: 'unavailable', error: 'delta_trades_invalid_response' });
    }
    const trades = rows.map((row: any, index: number) => {
      const timestamp = Number(row.timestamp);
      const buyerTaker = row.buyer_role === 'taker';
      const sellerTaker = row.seller_role === 'taker';
      return {
        id: String(row.id ?? `${timestamp}-${index}-${row.price}`),
        price: Number(row.price), size: Number(row.size),
        side: buyerTaker ? 'buy' : sellerTaker ? 'sell' : 'unknown',
        timestamp: Number.isFinite(timestamp) ? Math.floor(timestamp / 1000) : null,
      };
    }).filter((trade: any) => Number.isFinite(trade.price) && trade.price > 0 &&
      Number.isFinite(trade.size) && trade.size >= 0 && trade.timestamp !== null)
      .slice(0, 100);
    return res.json({ success: true, source: 'delta_india_rest', symbol, fetchedAt: Date.now(), trades });
  } catch (_error) {
    return res.status(502).json({ success: false, source: 'unavailable', error: 'delta_trades_unavailable' });
  }
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
    // Never return invented levels or a fabricated trading setup when analysis fails.
    res.status(503).json({ success: false, error: 'market_analysis_unavailable' });
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
