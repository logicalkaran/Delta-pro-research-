import { TradeEvent, OrderBookState, DeltaBar } from '../types/microstructure';
import { reconstructOrderBook } from './orderBookEngine';
import { aggregateTradesIntoDeltaBars } from './deltaEngine';

/**
 * High-Fidelity Microstructure Market Data Generator for BTCUSDT
 * Generates realistic trades, order-book states, and JSONL streams.
 */

export function generateSyntheticMicrostructureData(
  sampleCount: number = 240,
  basePrice: number = 94350
): {
  trades: TradeEvent[];
  orderBooks: OrderBookState[];
  deltaBars: DeltaBar[];
  rawJsonlLines: string[];
} {
  const trades: TradeEvent[] = [];
  const orderBooks: OrderBookState[] = [];
  const rawJsonlLines: string[] = [];

  const now = Date.now();
  const startTime = now - sampleCount * 60 * 1000;
  let currentPrice = basePrice;
  let sequenceId = 100000;

  for (let i = 0; i < sampleCount; i++) {
    const barTimestamp = startTime + i * 60 * 1000;
    const tradesInBar = Math.floor(Math.random() * 8 + 4);

    // Random walk with occasional micro-trends
    const trendBias = Math.sin(i / 15) * 0.8;
    const volatility = currentPrice * 0.0006;

    for (let t = 0; t < tradesInBar; t++) {
      sequenceId++;
      const tradeTimestamp = barTimestamp + Math.floor((t / tradesInBar) * 58000) + Math.floor(Math.random() * 1000);
      const isBuy = Math.random() + trendBias * 0.2 > 0.48;

      const priceDelta = (isBuy ? 1 : -1) * (Math.random() * volatility * 0.4);
      currentPrice = Math.max(1000, currentPrice + priceDelta);

      const size = Number((Math.random() * 2.8 + 0.1).toFixed(4));
      const tradeId = `t-${sequenceId}`;

      const trade: TradeEvent = {
        tradeId,
        symbol: 'BTCUSDT',
        price: Number(currentPrice.toFixed(2)),
        size,
        side: isBuy ? 'buy' : 'sell',
        exchangeTimestamp: tradeTimestamp,
        localReceiveTimestamp: tradeTimestamp + Math.floor(Math.random() * 8 + 4), // ~8ms latency
        isAggressiveBuy: isBuy,
        isAggressiveSell: !isBuy,
        value: Number((currentPrice * size).toFixed(2)),
      };
      trades.push(trade);

      // JSONL line
      rawJsonlLines.push(
        JSON.stringify({
          eventType: 'trade',
          symbol: 'BTCUSDT',
          exchangeTimestamp: trade.exchangeTimestamp,
          localReceiveTimestamp: trade.localReceiveTimestamp,
          sequenceId,
          price: trade.price,
          size: trade.size,
          side: trade.side,
        })
      );
    }

    // Generate Order Book Snapshot at end of bar
    sequenceId++;
    const bestBid = Number((currentPrice - 0.5).toFixed(2));
    const bestAsk = Number((currentPrice + 0.5).toFixed(2));

    const rawBids: [number, number][] = [];
    const rawAsks: [number, number][] = [];

    for (let lvl = 0; lvl < 25; lvl++) {
      const bPrice = Number((bestBid - lvl * 1.0).toFixed(2));
      const aPrice = Number((bestAsk + lvl * 1.0).toFixed(2));
      const bSize = Number((Math.random() * 3.5 + 0.5).toFixed(4));
      const aSize = Number((Math.random() * 3.5 + 0.5).toFixed(4));
      rawBids.push([bPrice, bSize]);
      rawAsks.push([aPrice, aSize]);
    }

    const ob = reconstructOrderBook('BTCUSDT', barTimestamp + 59000, sequenceId, rawBids, rawAsks);
    orderBooks.push(ob);

    // JSONL book snapshot
    rawJsonlLines.push(
      JSON.stringify({
        eventType: 'depth_snapshot',
        symbol: 'BTCUSDT',
        exchangeTimestamp: ob.timestamp,
        localReceiveTimestamp: ob.timestamp + 6,
        sequenceId,
        bids: rawBids.slice(0, 10),
        asks: rawAsks.slice(0, 10),
      })
    );
  }

  // Aggregate into delta bars
  const deltaBars = aggregateTradesIntoDeltaBars(trades, 60);

  // Link order-book imbalance to delta bars
  for (let i = 0; i < Math.min(deltaBars.length, orderBooks.length); i++) {
    deltaBars[i].orderBookImbalance = orderBooks[i].depthImbalance10;
  }

  return {
    trades,
    orderBooks,
    deltaBars,
    rawJsonlLines,
  };
}
