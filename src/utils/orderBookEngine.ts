import { BookLevel, OrderBookState } from '../types/microstructure';

/**
 * Order-Book Reconstruction and Microstructure Feature Calculator
 */

export function reconstructOrderBook(
  symbol: string,
  timestamp: number,
  sequenceId: number,
  rawBids: [number, number][], // [price, size]
  rawAsks: [number, number][]
): OrderBookState {
  // Sort bids descending, asks ascending
  const bids: BookLevel[] = rawBids
    .filter(([p, s]) => p > 0 && s > 0)
    .sort((a, b) => b[0] - a[0])
    .map(([price, size]) => ({ price, size }));

  const asks: BookLevel[] = rawAsks
    .filter(([p, s]) => p > 0 && s > 0)
    .sort((a, b) => a[0] - b[0])
    .map(([price, size]) => ({ price, size }));

  const bestBid = bids.length > 0 ? bids[0].price : 0;
  const bestAsk = asks.length > 0 ? asks[0].price : 0;
  const isCrossed = bestBid > 0 && bestAsk > 0 && bestBid >= bestAsk;

  const midPrice = bestBid > 0 && bestAsk > 0 ? (bestBid + bestAsk) / 2 : Math.max(bestBid, bestAsk);
  const spread = bestBid > 0 && bestAsk > 0 ? Math.max(0, bestAsk - bestBid) : 0;
  const spreadBps = midPrice > 0 ? (spread / midPrice) * 10000 : 0;

  // Level 1 sizes
  const l1BidSize = bids.length > 0 ? bids[0].size : 0;
  const l1AskSize = asks.length > 0 ? asks[0].size : 0;

  // Microprice: Volume-weighted midprice
  let microprice = midPrice;
  if (l1BidSize + l1AskSize > 0) {
    microprice = (l1AskSize * bestBid + l1BidSize * bestAsk) / (l1BidSize + l1AskSize);
  }

  // Depths at 5, 10, 20 levels
  const sumDepth = (levels: BookLevel[], count: number) =>
    levels.slice(0, count).reduce((sum, lvl) => sum + lvl.size, 0);

  const bidDepth5 = sumDepth(bids, 5);
  const askDepth5 = sumDepth(asks, 5);
  const depthImbalance5 =
    bidDepth5 + askDepth5 > 0 ? (bidDepth5 - askDepth5) / (bidDepth5 + askDepth5) : 0;

  const bidDepth10 = sumDepth(bids, 10);
  const askDepth10 = sumDepth(asks, 10);
  const depthImbalance10 =
    bidDepth10 + askDepth10 > 0 ? (bidDepth10 - askDepth10) / (bidDepth10 + askDepth10) : 0;

  const bidDepth20 = sumDepth(bids, 20);
  const askDepth20 = sumDepth(asks, 20);
  const depthImbalance20 =
    bidDepth20 + askDepth20 > 0 ? (bidDepth20 - askDepth20) / (bidDepth20 + askDepth20) : 0;

  // Liquidity concentration: top 3 levels versus top 20 levels
  const top3Depth = sumDepth(bids, 3) + sumDepth(asks, 3);
  const top20Depth = bidDepth20 + askDepth20;
  const liquidityConcentration = top20Depth > 0 ? top3Depth / top20Depth : 1.0;

  return {
    symbol,
    timestamp,
    sequenceId,
    bids,
    asks,
    bestBid,
    bestAsk,
    midPrice: Number(midPrice.toFixed(2)),
    spread: Number(spread.toFixed(2)),
    spreadBps: Number(spreadBps.toFixed(2)),
    microprice: Number(microprice.toFixed(2)),
    bidDepth5: Number(bidDepth5.toFixed(4)),
    askDepth5: Number(askDepth5.toFixed(4)),
    depthImbalance5: Number(depthImbalance5.toFixed(4)),
    bidDepth10: Number(bidDepth10.toFixed(4)),
    askDepth10: Number(askDepth10.toFixed(4)),
    depthImbalance10: Number(depthImbalance10.toFixed(4)),
    bidDepth20: Number(bidDepth20.toFixed(4)),
    askDepth20: Number(askDepth20.toFixed(4)),
    depthImbalance20: Number(depthImbalance20.toFixed(4)),
    liquidityConcentration: Number(liquidityConcentration.toFixed(4)),
    isCrossed,
  };
}
