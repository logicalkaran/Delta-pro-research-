import { RawMarketEvent, DataQualityReport, TradeEvent, OrderBookState } from '../types/microstructure';
import { reconstructOrderBook } from './orderBookEngine';

export function validateMarketDataBatch(rawLines: string[]): {
  report: DataQualityReport;
  validTrades: TradeEvent[];
  validBooks: OrderBookState[];
} {
  let validRecordsCount = 0;
  let rejectedRecordsCount = 0;
  let missingTimestampCount = 0;
  let duplicateEventCount = 0;
  let outOfOrderCount = 0;
  let sequenceGapCount = 0;
  let crossedBookCount = 0;
  let negativeQuantityCount = 0;

  const rejectionLog: DataQualityReport['rejectionLog'] = [];
  const seenEventIds = new Set<string>();

  let prevExchangeTimestamp = 0;
  let prevSequenceId = 0;
  let totalDriftMs = 0;
  let driftCount = 0;
  let maxDriftMs = 0;

  const validTrades: TradeEvent[] = [];
  const validBooks: OrderBookState[] = [];

  for (let i = 0; i < rawLines.length; i++) {
    const rawLine = rawLines[i].trim();
    if (!rawLine) continue;

    let parsed: any = null;
    try {
      parsed = JSON.parse(rawLine);
    } catch (e) {
      // Try CSV parsing: timestamp,symbol,price,size,side,seq
      const parts = rawLine.split(',');
      if (parts.length >= 5) {
        parsed = {
          eventType: 'trade',
          symbol: parts[1] || 'BTCUSDT',
          exchangeTimestamp: Number(parts[0]),
          localReceiveTimestamp: Number(parts[0]) + 15,
          sequenceId: parts[5] ? Number(parts[5]) : i + 1,
          price: Number(parts[2]),
          size: Number(parts[3]),
          side: parts[4]?.toLowerCase() === 'buy' ? 'buy' : 'sell',
        };
      }
    }

    if (!parsed) {
      rejectedRecordsCount++;
      rejectionLog.push({
        timestamp: Date.now(),
        sequenceId: i,
        reason: 'Malformed JSON/CSV format',
        rawSample: rawLine.substring(0, 100),
      });
      continue;
    }

    // Check timestamps
    const exchangeTs = Number(parsed.exchangeTimestamp || parsed.time || parsed.timestamp);
    const localTs = Number(parsed.localReceiveTimestamp || parsed.receivedAt || exchangeTs + 12);

    if (!exchangeTs || isNaN(exchangeTs)) {
      missingTimestampCount++;
      rejectedRecordsCount++;
      rejectionLog.push({
        timestamp: Date.now(),
        sequenceId: parsed.sequenceId || i,
        reason: 'Missing or NaN exchangeTimestamp',
        rawSample: rawLine.substring(0, 100),
      });
      continue;
    }

    // Timestamp drift
    if (localTs && localTs >= exchangeTs) {
      const drift = localTs - exchangeTs;
      totalDriftMs += drift;
      driftCount++;
      if (drift > maxDriftMs) maxDriftMs = drift;
    }

    // Duplicate check
    const eventId = String(parsed.eventId || parsed.id || `${exchangeTs}-${parsed.sequenceId || i}`);
    if (seenEventIds.has(eventId)) {
      duplicateEventCount++;
      rejectedRecordsCount++;
      rejectionLog.push({
        timestamp: exchangeTs,
        sequenceId: parsed.sequenceId || i,
        reason: `Duplicate event identifier ${eventId}`,
        rawSample: rawLine.substring(0, 100),
      });
      continue;
    }
    seenEventIds.add(eventId);

    // Out-of-order check
    if (prevExchangeTimestamp > 0 && exchangeTs < prevExchangeTimestamp) {
      outOfOrderCount++;
      // We don't reject strictly if it's within 100ms jitter, but flag warning
    }
    prevExchangeTimestamp = exchangeTs;

    // Sequence gap check
    const seqId = Number(parsed.sequenceId || i + 1);
    if (prevSequenceId > 0 && seqId !== prevSequenceId + 1 && seqId > prevSequenceId) {
      sequenceGapCount += (seqId - prevSequenceId - 1);
    }
    prevSequenceId = seqId;

    // Trade validation
    if (parsed.eventType === 'trade' || parsed.price !== undefined) {
      const price = Number(parsed.price);
      const size = Number(parsed.size || parsed.qty || parsed.amount);
      const side = String(parsed.side || '').toLowerCase() === 'buy' ? 'buy' : 'sell';

      if (price <= 0 || isNaN(price) || size <= 0 || isNaN(size)) {
        negativeQuantityCount++;
        rejectedRecordsCount++;
        rejectionLog.push({
          timestamp: exchangeTs,
          sequenceId: seqId,
          reason: `Invalid price (${price}) or size (${size})`,
          rawSample: rawLine.substring(0, 100),
        });
        continue;
      }

      validTrades.push({
        tradeId: eventId,
        symbol: parsed.symbol || 'BTCUSDT',
        price,
        size,
        side,
        exchangeTimestamp: exchangeTs,
        localReceiveTimestamp: localTs,
        isAggressiveBuy: side === 'buy',
        isAggressiveSell: side === 'sell',
        value: price * size,
      });

      validRecordsCount++;
    } else if (parsed.eventType === 'depth_snapshot' || parsed.bids || parsed.asks) {
      // Order book state validation
      const rawBids = (parsed.bids || []).map((b: any) => [Number(b[0] || b.price), Number(b[1] || b.size)]);
      const rawAsks = (parsed.asks || []).map((a: any) => [Number(a[0] || a.price), Number(a[1] || a.size)]);

      const book = reconstructOrderBook(parsed.symbol || 'BTCUSDT', exchangeTs, seqId, rawBids, rawAsks);
      if (book.isCrossed) {
        crossedBookCount++;
        rejectedRecordsCount++;
        rejectionLog.push({
          timestamp: exchangeTs,
          sequenceId: seqId,
          reason: `Crossed order book: Best bid $${book.bestBid} >= Best ask $${book.bestAsk}`,
          rawSample: rawLine.substring(0, 100),
        });
        continue;
      }

      validBooks.push(book);
      validRecordsCount++;
    } else {
      validRecordsCount++;
    }
  }

  const total = validRecordsCount + rejectedRecordsCount;
  const healthScore = total > 0 ? Math.max(0, Math.min(100, Math.round(((validRecordsCount) / total) * 100 - (sequenceGapCount > 0 ? 5 : 0)))) : 100;

  return {
    report: {
      totalRecordsProcessed: total,
      validRecordsCount,
      rejectedRecordsCount,
      missingTimestampCount,
      duplicateEventCount,
      outOfOrderCount,
      sequenceGapCount,
      crossedBookCount,
      negativeQuantityCount,
      maxTimestampDriftMs: maxDriftMs,
      meanTimestampDriftMs: driftCount > 0 ? Math.round(totalDriftMs / driftCount) : 0,
      rejectionLog: rejectionLog.slice(0, 50),
      healthScore,
    },
    validTrades,
    validBooks,
  };
}
