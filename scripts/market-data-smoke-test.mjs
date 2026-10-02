import assert from 'node:assert/strict';

const baseUrl = process.env.BASE_URL || 'http://127.0.0.1:3000';
const symbol = process.env.MARKET_SYMBOL || 'BTCUSD';

async function getJson(path) {
  const response = await fetch(new URL(path, baseUrl), { signal: AbortSignal.timeout(15000) });
  const body = await response.json();
  assert.equal(response.ok, true, `${path} returned HTTP ${response.status}: ${JSON.stringify(body)}`);
  assert.equal(body.success, true, `${path} did not report success: ${JSON.stringify(body)}`);
  return body;
}

const [tickers, candles, book, trades] = await Promise.all([
  getJson('/api/delta/tickers'),
  getJson(`/api/delta/candles?symbol=${encodeURIComponent(symbol)}&resolution=1h`),
  getJson(`/api/delta/orderbook/${encodeURIComponent(symbol)}`),
  getJson(`/api/delta/trades/${encodeURIComponent(symbol)}`),
]);

assert.equal(tickers.source, 'delta_live');
assert.ok(tickers.tickers.some((ticker) => ticker.symbol === symbol), `ticker missing for ${symbol}`);
assert.equal(candles.source, 'delta_live');
assert.ok(Array.isArray(candles.candles) && candles.candles.length > 0);
assert.equal(book.source, 'delta_india_rest');
assert.ok(book.bids.length > 0 && book.asks.length > 0);
assert.ok(book.bids.every((level) => Number.isFinite(level.price) && Number.isFinite(level.size)));
assert.ok(book.bids.every((level, i, rows) => i === 0 || rows[i - 1].price >= level.price), 'bids are not descending');
assert.ok(book.asks.every((level, i, rows) => i === 0 || rows[i - 1].price <= level.price), 'asks are not ascending');
assert.ok(book.bids.every((level, i, rows) => i === 0 || level.total >= rows[i - 1].total), 'bid cumulative depth decreases');
assert.ok(book.asks.every((level, i, rows) => i === 0 || level.total >= rows[i - 1].total), 'ask cumulative depth decreases');
assert.equal(trades.source, 'delta_india_rest');
assert.ok(Array.isArray(trades.trades));
assert.ok(trades.trades.every((trade) => ['buy', 'sell', 'unknown'].includes(trade.side)));
assert.ok(trades.trades.every((trade) => Number.isFinite(trade.price) && Number.isFinite(trade.size) && Number.isFinite(trade.timestamp)));

console.log(JSON.stringify({
  status: 'PASS',
  symbol,
  liveTickerCount: tickers.tickers.length,
  candleCount: candles.candles.length,
  bidLevels: book.bids.length,
  askLevels: book.asks.length,
  recentTrades: trades.trades.length,
  source: 'Delta Exchange India public REST',
}, null, 2));
