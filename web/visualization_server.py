"""Live, read-only Delta Exchange India BTCUSD perpetual dashboard.
Market data is held in RAM only. No market snapshots, ticks, or logs are written.
No credentials, private endpoints, strategy evaluation, or order submission.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.parse
import urllib.request
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import websocket

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
HOST = "127.0.0.1"
PORT = 8791
SYMBOL = "BTCUSD"
REST = "https://api.india.delta.exchange"
WS_URL = "wss://public-socket.india.delta.exchange"
LOCK = threading.RLock()
TRADES = deque(maxlen=5000)
# Short rolling order-book event history; memory only, never written to disk.
BOOK_HISTORY = deque(maxlen=1200)
TIMEFRAMES = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}
HISTORY_TTL = {"1m": 30, "5m": 60, "15m": 180, "1h": 300, "4h": 600, "1d": 1800}
CANDLES_BY_TF = {tf: deque(maxlen=240) for tf in TIMEFRAMES}
CANDLE_FETCHED_AT = {tf: 0.0 for tf in TIMEFRAMES}
FEED = {
    "connected": False, "connection_state": "STARTING", "last_message_at": None,
    "last_error": None, "market": {}, "book": {}, "last_trade": {},
    "mark_price": None, "funding": {}, "channel_seen": {}, "cvd_since_start": 0.0,
    "timestamp_missing_count": 0, "book_rejected_crossed": 0,
}
STOP = threading.Event()
# Forecasts, price snapshots and matured outcomes are deliberately RAM-only.
FORECASTS = {300: deque(maxlen=120), 600: deque(maxlen=120)}
FORECAST_ERRORS = {300: deque(maxlen=120), 600: deque(maxlen=120)}
PRICE_HISTORY = deque(maxlen=7200)  # bounded mid-price samples, typically ~4 hours at 2s
EVAL_MISSED = {300: 0, 600: 0}
LAST_FORECAST_AT = {300: 0.0, 600: 0.0}
FORECAST_TARGET_TOLERANCE_SECONDS = 3.0
# Precompute state off the HTTP request path; clients receive a cached RAM snapshot.
STATE_CACHE_LOCK = threading.Lock()
STATE_CACHE = {"json": b"{}", "updated_at": 0.0}


def epoch_from_exchange(value):
    try:
        n = float(value)
        if n <= 0 or n != n or abs(n) == float("inf"):
            return None
        magnitude = abs(n)
        if magnitude >= 100_000_000_000_000_000: return n / 1_000_000_000  # nanoseconds
        if magnitude >= 100_000_000_000_000: return n / 1_000_000  # microseconds
        if magnitude >= 100_000_000_000: return n / 1_000  # milliseconds
        return n
    except (TypeError, ValueError):
        return None


def num(value, default=0.0):
    try:
        x = float(value)
        return x if x == x and abs(x) != float("inf") else default
    except (TypeError, ValueError):
        return default


def levels(raw):
    out = []
    if isinstance(raw, list):
        for row in raw[:15]:
            try:
                p, s = num(row[0]), num(row[1])
                if p > 0 and s >= 0:
                    out.append([p, s])
            except (IndexError, TypeError):
                continue
    return out


def update_book(bids, asks, ts=None):
    bids, asks = levels(bids), levels(asks)
    bids.sort(key=lambda z: z[0], reverse=True)
    asks.sort(key=lambda z: z[0])
    if not bids or not asks:
        return
    bid, ask = bids[0][0], asks[0][0]
    # Reject crossed/locked snapshots rather than disguising them as zero spread.
    if bid >= ask:
        with LOCK:
            FEED["book_rejected_crossed"] = int(FEED.get("book_rejected_crossed", 0)) + 1
        return
    exchange_ts = epoch_from_exchange(ts)
    if exchange_ts is None:
        with LOCK:
            FEED["timestamp_missing_count"] = int(FEED.get("timestamp_missing_count", 0)) + 1
        return
    bd5, ad5 = sum(x[1] for x in bids[:5]), sum(x[1] for x in asks[:5])
    bd10, ad10 = sum(x[1] for x in bids[:10]), sum(x[1] for x in asks[:10])
    with LOCK:
        FEED["book"] = {
            "symbol": SYMBOL, "updated_at": exchange_ts,
            "best_bid": bid, "best_ask": ask, "mid_price": (bid + ask) / 2,
            "spread": max(0.0, ask - bid), "bids_l5": bids[:5], "asks_l5": asks[:5],
            "bid_depth_5": bd5, "ask_depth_5": ad5, "bid_depth_10": bd10, "ask_depth_10": ad10,
            "imbalance_5": (bd5 - ad5) / (bd5 + ad5) if bd5 + ad5 else 0.0,
            "imbalance_10": (bd10 - ad10) / (bd10 + ad10) if bd10 + ad10 else 0.0,
            "bid_levels": len(bids), "ask_levels": len(asks),
            "bid_size": bids[0][1], "ask_size": asks[0][1],
        }
        m = FEED["market"]
        m.update({"symbol": SYMBOL, "best_bid": bid, "best_ask": ask,
                  "mid_price": (bid + ask) / 2, "spread": max(0.0, ask - bid),
                  "bid_size": bids[0][1], "ask_size": asks[0][1],
                  "event_type": "ob_l2", "updated_at": epoch_from_exchange(ts)})
        FEED["channel_seen"]["ob_l2"] = time.time()
        FEED["last_message_at"] = time.time()
        BOOK_HISTORY.append({
            "timestamp": time.time(), "mid_price": (bid + ask) / 2,
            "spread": max(0.0, ask - bid),
            "imbalance_5": FEED["book"]["imbalance_5"],
            "imbalance_10": FEED["book"]["imbalance_10"],
            "bid_depth_5": bd5, "ask_depth_5": ad5,
            "bid_depth_10": bd10, "ask_depth_10": ad10,
        })


def on_message(_ws, raw):
    try:
        msg = json.loads(raw)
        if not isinstance(msg, dict):
            return
        typ = str(msg.get("type", ""))
        if typ in ("subscriptions", "pong", "heartbeat", "success", "error"):
            if typ == "error":
                with LOCK:
                    FEED["last_error"] = str(msg)[:240]
            return
        sy = str(msg.get("sy", msg.get("symbol", ""))).upper()
        if sy and sy not in (SYMBOL, "MARK:" + SYMBOL):
            return
        now = time.time()
        with LOCK:
            FEED["last_message_at"] = now
            FEED["channel_seen"][typ] = now

        if typ == "ob_l1":
            bid, ask = num(msg.get("bp")), num(msg.get("ap"))
            if bid > 0 and ask > bid:
                with LOCK:
                    m = FEED["market"]
                    m.update({"symbol": SYMBOL, "best_bid": bid, "best_ask": ask,
                              "bid_size": num(msg.get("bs")), "ask_size": num(msg.get("as")),
                              "mid_price": (bid + ask) / 2, "spread": max(0.0, ask - bid),
                              "event_type": typ, "updated_at": epoch_from_exchange(msg.get("ts"))})
                    FEED["channel_seen"][typ] = now
        elif typ == "ob_l2":
            update_book(msg.get("b", []), msg.get("a", []), msg.get("ts"))
        elif typ == "trades":
            price, size = num(msg.get("p")), num(msg.get("s"))
            # Delta's r field is buyer role: buyer taker => buy aggression;
            # buyer maker => sell aggression. Unknown role is not guessed.
            role = str(msg.get("r", "")).lower()
            side = "buy" if role in ("t", "taker") else "sell" if role in ("m", "maker") else "unknown"
            ts = epoch_from_exchange(msg.get("t", msg.get("ts")))
            if ts is None:
                with LOCK:
                    FEED["timestamp_missing_count"] = int(FEED.get("timestamp_missing_count", 0)) + 1
                return
            if price > 0 and size >= 0:
                trade = {"timestamp": ts, "price": price, "size": size, "side": side}
                with LOCK:
                    TRADES.append(trade)
                    FEED["last_trade"] = trade
                    FEED["cvd_since_start"] += size if side == "buy" else -size if side == "sell" else 0.0
                    FEED["market"].update({"symbol": SYMBOL, "last_price": price,
                        "last_trade_size": size, "last_trade_side": side,
                        "updated_at": now, "event_type": typ})
        elif typ.startswith("candlestick_"):
            # Delta sends candle updates with event timestamps; normalize to the
            # candle's minute-open epoch so updates replace one bar instead of
            # appending a new pseudo-candle for every WebSocket message.
            ts = epoch_from_exchange(msg.get("ts"))
            if ts is None:
                with LOCK:
                    FEED["timestamp_missing_count"] = int(FEED.get("timestamp_missing_count", 0)) + 1
                return
            ts = int(ts // 60) * 60
            candle = {"timestamp": int(ts), "open": num(msg.get("o")), "high": num(msg.get("h")),
                      "low": num(msg.get("l")), "close": num(msg.get("c")), "volume": num(msg.get("v"))}
            if candle["timestamp"] > 0 and min(candle["open"], candle["high"], candle["low"], candle["close"]) > 0:
                # The subscribed live candle channel is 1m; other frames use public REST.
                with LOCK:
                    frame = CANDLES_BY_TF["1m"]
                    if frame and frame[-1]["timestamp"] == candle["timestamp"]:
                        frame[-1] = candle
                    elif not frame or frame[-1]["timestamp"] < candle["timestamp"]:
                        frame.append(candle)
        elif typ == "mark_price":
            with LOCK:
                FEED["mark_price"] = num(msg.get("p"))
        elif typ == "funding_rate":
            with LOCK:
                FEED["funding"] = {"rate": num(msg.get("fr")), "next_funding_at": epoch_from_exchange(msg.get("nfr")),
                                   "interval_seconds": num(msg.get("fi"))}
    except Exception as exc:
        with LOCK:
            FEED["last_error"] = type(exc).__name__ + ": " + str(exc)[:180]


def on_open(ws):
    with LOCK:
        FEED["connected"] = True
        FEED["connection_state"] = "CONNECTED"
        FEED["last_error"] = None
    ws.send(json.dumps({"type": "subscribe", "payload": {"channels": [
        {"name": "ob_l1", "symbols": [SYMBOL]},
        {"name": "ob_l2", "symbols": [SYMBOL]},
        {"name": "trades", "symbols": [SYMBOL]},
        {"name": "candlestick_1m", "symbols": [SYMBOL]},
        {"name": "mark_price", "symbols": ["MARK:" + SYMBOL]},
        {"name": "funding_rate", "symbols": [SYMBOL]},
    ]}}))


def on_error(_ws, error):
    with LOCK:
        FEED["last_error"] = str(error)[:240]
        FEED["connection_state"] = "RECONNECTING"


def on_close(_ws, _code, _message):
    with LOCK:
        FEED["connected"] = False
        FEED["connection_state"] = "RECONNECTING"


def websocket_worker():
    while not STOP.is_set():
        try:
            ws = websocket.WebSocketApp(WS_URL, on_open=on_open, on_message=on_message,
                                        on_error=on_error, on_close=on_close)
            ws.run_forever(ping_interval=25, ping_timeout=8)
        except Exception as exc:
            with LOCK:
                FEED["connected"] = False
                FEED["connection_state"] = "RECONNECTING"
                FEED["last_error"] = type(exc).__name__ + ": " + str(exc)[:180]
        STOP.wait(4)


def history_worker():
    """Refresh 1m/5m/15m/1h public candles in RAM, with per-frame TTLs."""
    while not STOP.is_set():
        now = time.time()
        for tf, seconds in TIMEFRAMES.items():
            if STOP.is_set():
                break
            with LOCK:
                due = now - CANDLE_FETCHED_AT[tf] >= HISTORY_TTL[tf]
            if not due:
                continue
            try:
                end = int(time.time())
                # Keep roughly 240 bars per frame; the REST result is never written to disk.
                lookback = seconds * 240
                query = urllib.parse.urlencode({"resolution": tf, "symbol": SYMBOL,
                                                "start": end - lookback, "end": end})
                req = urllib.request.Request(REST + "/v2/history/candles?" + query,
                    headers={"Accept": "application/json", "User-Agent": "read-only-btc-dashboard/1.0"})
                with urllib.request.urlopen(req, timeout=8) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                if payload.get("success") is False:
                    raise RuntimeError("Delta candle endpoint returned success=false")
                rows = []
                for raw in payload.get("result", []):
                    try:
                        ts = int(raw["time"])
                        row = {"timestamp": ts, "open": num(raw["open"]), "high": num(raw["high"]),
                               "low": num(raw["low"]), "close": num(raw["close"]),
                               "volume": num(raw.get("volume"))}
                        if ts > 0 and min(row["open"], row["high"], row["low"], row["close"]) > 0:
                            rows.append(row)
                    except (KeyError, TypeError, ValueError):
                        continue
                by_ts = {row["timestamp"]: row for row in rows}
                ordered = [by_ts[t] for t in sorted(by_ts)][-240:]
                if not ordered:
                    raise RuntimeError("empty valid candle response for " + tf)
                with LOCK:
                    frame = CANDLES_BY_TF[tf]
                    if tf == "1m":
                        # REST fills gaps and WebSocket remains the most recent source.
                        merged = {row["timestamp"]: row for row in ordered}
                        merged.update({row["timestamp"]: row for row in frame})
                        ordered = [merged[t] for t in sorted(merged)][-240:]
                    frame.clear()
                    frame.extend(ordered)
                    CANDLE_FETCHED_AT[tf] = time.time()
                    FEED["channel_seen"]["candles_" + tf] = time.time()
            except Exception as exc:
                with LOCK:
                    FEED["last_error"] = "Candle " + tf + " refresh: " + type(exc).__name__
        STOP.wait(5)


def build_five_minute_forecast(now, market, book, trades, candle_frames, windows, mark, funding, feed_fresh, horizon_seconds=300, book_dynamics=None):
    """Transparent untrained baseline; separate RAM-only 5m/10m evaluation."""
    if not feed_fresh:
        return {"available": False, "reason": "Live feed is stale or disconnected; forecast paused", "horizon_seconds": horizon_seconds}
    mid = num(book.get("mid_price")) or num(market.get("mid_price")) or num(market.get("last_price")) or num(mark)
    if mid <= 0:
        rows = candle_frames.get("1m", [])
        mid = num(rows[-1].get("close")) if rows else 0.0
    if mid <= 0:
        return {"available": False, "reason": "Waiting for a valid live price", "horizon_seconds": horizon_seconds}

    # Multi-lookback, volatility-aware momentum: avoid letting one noisy candle dominate.
    # Returns are shrunk with square-root horizon scaling rather than linear extrapolation.
    horizon_minutes = horizon_seconds / 60.0
    frame_specs = (("1m", (1, 3, 5, 10), 0.42), ("5m", (1, 2, 3), 0.33),
                   ("15m", (1, 2), 0.17), ("1h", (1, 2), 0.08))
    components, weighted, weight_total, directional_votes = {}, 0.0, 0.0, []
    for tf, lookbacks, tf_weight in frame_specs:
        rows = candle_frames.get(tf, [])
        closes = [num(r.get("close")) for r in rows if num(r.get("close")) > 0]
        tf_minutes = TIMEFRAMES[tf] / 60.0
        observations = []
        for lookback in lookbacks:
            if len(closes) <= lookback:
                continue
            raw_bps = (closes[-1] / closes[-1-lookback] - 1.0) * 10000.0
            elapsed_minutes = tf_minutes * lookback
            # Shrink extrapolation for long horizons; do not assume returns compound linearly.
            equivalent = raw_bps * min(1.0, (horizon_minutes / max(elapsed_minutes, 1.0)) ** 0.5)
            observations.append({"lookback_bars": lookback, "elapsed_minutes": elapsed_minutes,
                                 "return_bps": raw_bps, "horizon_component_bps": equivalent})
        if observations:
            # Recent short and medium lookbacks both contribute; median resists outlier bars.
            vals = sorted(x["horizon_component_bps"] for x in observations)
            robust = vals[len(vals)//2] if len(vals) % 2 else (vals[len(vals)//2-1] + vals[len(vals)//2]) / 2.0
            components[tf] = {"observations": observations, "robust_component_bps": robust,
                              "lookbacks_available": len(observations)}
            weighted += robust * tf_weight
            weight_total += tf_weight
            directional_votes.append((1 if robust > 0 else -1 if robust < 0 else 0, tf_weight))
    if weight_total <= 0:
        return {"available": False, "reason": "Waiting for multiple usable candle lookbacks", "horizon_seconds": horizon_seconds}
    drift_bps = weighted / weight_total
    vote_weight = sum(w for vote, w in directional_votes if vote)
    directional_agreement = (sum(w for vote, w in directional_votes if vote > 0) -
                              sum(w for vote, w in directional_votes if vote < 0)) / vote_weight if vote_weight else 0.0
    agreement_strength = abs(directional_agreement)
    # When timeframes disagree, shrink the directional forecast toward zero instead of forcing a side.
    drift_bps *= 0.35 + 0.65 * agreement_strength

    # Add small, bounded microstructure adjustments from current live order book and taker flow.
    imbalance = num(book.get("imbalance_5"))
    imbalance10 = num(book.get("imbalance_10"))
    flow = windows.get("30", {})
    flow_total = num(flow.get("buy_volume")) + num(flow.get("sell_volume"))
    flow_norm = num(flow.get("delta")) / flow_total if flow_total > 0 else 0.0
    flow_norm = max(-1.0, min(1.0, flow_norm))
    # Estimate recent 1m absolute movement to scale the bounded microstructure terms.
    one = candle_frames.get("1m", [])[-21:]
    abs_returns = []
    for i in range(1, len(one)):
        prev, cur = num(one[i-1].get("close")), num(one[i].get("close"))
        if prev > 0 and cur > 0:
            abs_returns.append(abs(cur / prev - 1.0) * 10000.0)
    sorted_abs = sorted(abs_returns)
    vol1m_bps = (sorted_abs[len(sorted_abs)//2] if len(sorted_abs) % 2 else (sorted_abs[len(sorted_abs)//2-1] + sorted_abs[len(sorted_abs)//2]) / 2.0) if sorted_abs else 0.0
    micro_scale = max(0.25, min(8.0, vol1m_bps))
    # Operational volatility buckets for stratified diagnostics; thresholds are not calibrated.
    volatility_regime = "LOW" if vol1m_bps < 2.0 else ("NORMAL" if vol1m_bps < 8.0 else "HIGH")
    decay = (300.0 / horizon_seconds) ** 0.5
    book_adjustment = max(-1.0, min(1.0, (0.65*imbalance + 0.35*imbalance10))) * micro_scale * 0.20 * decay
    flow_adjustment = flow_norm * micro_scale * 0.15 * decay
    dynamics = book_dynamics or {}
    dyn15, dyn30 = dynamics.get("15", {}), dynamics.get("30", {})
    imbalance_change = (0.65*num(dyn15.get("imbalance_5_change")) if dyn15.get("available") else 0.0) + (0.35*num(dyn30.get("imbalance_5_change")) if dyn30.get("available") else 0.0)
    book_dynamics_adjustment = max(-0.5, min(0.5, imbalance_change)) * micro_scale * 0.10 * decay
    mark_basis_bps = ((num(mark) / mid) - 1.0) * 10000.0 if num(mark) > 0 else 0.0
    # Mark/funding are weak contextual inputs only; their contributions are deliberately tiny and bounded.
    mark_adjustment = max(-0.5, min(0.5, mark_basis_bps * 0.05)) * decay
    funding_adjustment = max(-0.25, min(0.25, -num(funding.get("rate")) * 10000.0 * 0.02)) * decay if funding else 0.0
    raw_forecast_bps = drift_bps + book_adjustment + flow_adjustment + book_dynamics_adjustment + mark_adjustment + funding_adjustment
    # Bound extrapolation; longer horizon gets a wider but sublinear movement cap.
    cap = max(2.0, vol1m_bps * 2.5 * (horizon_seconds / 300.0) ** 0.5)
    forecast_bps = max(-cap, min(cap, raw_forecast_bps))
    predicted = mid * (1.0 + forecast_bps / 10000.0)
    # Approximate range is volatility-based, not a calibrated confidence interval.
    range_bps = max(2.0, vol1m_bps * (horizon_seconds/60.0)**0.5 * 1.5)
    # Coverage is based on usable multi-lookback components, not merely candle presence.
    coverage = len(components) / len(frame_specs)
    spread = num(book.get("spread"))
    spread_bps = spread / mid * 10000.0 if spread >= 0 else None
    # Illustrative friction hurdle; actual fee tier, slippage and fills may differ.
    estimated_round_trip_cost_bps = 11.8 + (spread_bps if spread_bps is not None else 0.0) + 4.0
    estimated_net_move_bps = abs(forecast_bps) - estimated_round_trip_cost_bps
    latest_trade_age = max(0.0, now - trades[-1]["timestamp"]) if trades else None
    result = {
        "available": True, "model": "transparent_blended_baseline_v3_multilookback", "experimental": True,
        "horizon_seconds": horizon_seconds, "issued_at": now, "reference_price": mid,
        "predicted_price": predicted, "predicted_change_bps": forecast_bps,
        "estimated_range_low": mid * (1.0 + (forecast_bps-range_bps)/10000.0),
        "estimated_range_high": mid * (1.0 + (forecast_bps+range_bps)/10000.0),
        "range_half_width_bps": range_bps, "input_coverage": coverage,
        "volatility_regime": volatility_regime, "median_abs_1m_move_bps": vol1m_bps,
        "timeframe_directional_agreement": directional_agreement,
        "timeframe_agreement_pct": agreement_strength * 100.0,
        "estimated_round_trip_cost_bps": estimated_round_trip_cost_bps,
        "estimated_net_move_after_cost_bps": estimated_net_move_bps,
        "cost_hurdle_cleared": estimated_net_move_bps > 0,
        "forecast_quality_note": "Agreement is directional consistency, not probability. Cost hurdle uses illustrative 11.8 bps fees + spread + 4 bps slippage.",
        "components": components, "microstructure": {"book_imbalance_l5": imbalance,
            "book_imbalance_l10": imbalance10, "aggressive_flow_delta_30s": num(flow.get("delta")),
            "aggressive_flow_normalized_30s": flow_norm, "flow_samples_30s": int(num(flow.get("samples"))),
            "spread_bps": spread_bps, "median_abs_1m_move_bps": vol1m_bps,
            "book_adjustment_bps": book_adjustment, "flow_adjustment_bps": flow_adjustment,
            "book_dynamics_adjustment_bps": book_dynamics_adjustment, "book_dynamics": dynamics,
            "mark_basis_bps": mark_basis_bps, "mark_adjustment_bps": mark_adjustment,
            "funding_adjustment_bps": funding_adjustment},
        "funding_rate": num(funding.get("rate")) if funding else None,
        "mark_price": num(mark) if mark else None,
        "last_trade_age_seconds": latest_trade_age,
        "evaluation": {},
        "refresh_seconds": 2, "forecast_sample_interval_seconds": 10,
        "disclaimer": "Experimental untrained heuristic; horizon-scaled, not calibrated or validated for profitability. Range is not a calibrated prediction interval. No trading signal."
    }
    with LOCK:
        forecasts, errors = FORECASTS[horizon_seconds], FORECAST_ERRORS[horizon_seconds]
        # Evaluate against the closest RAM mid-price sample to the exact target time.
        # Wait through a small tolerance window; never substitute a much later price.
        while feed_fresh and forecasts:
            old = forecasts[0]
            target_at = old["issued_at"] + horizon_seconds
            if now < target_at + FORECAST_TARGET_TOLERANCE_SECONDS:
                break
            forecasts.popleft()
            closest = min(PRICE_HISTORY, key=lambda p: abs(p["timestamp"] - target_at)) if PRICE_HISTORY else None
            target_gap = abs(closest["timestamp"] - target_at) if closest else None
            if closest is None or target_gap > FORECAST_TARGET_TOLERANCE_SECONDS:
                EVAL_MISSED[horizon_seconds] += 1
                continue
            actual_change_bps = (closest["mid_price"] / old["reference_price"] - 1.0) * 10000.0
            predicted_bps = old["predicted_change_bps"]
            signed_error = actual_change_bps - predicted_bps
            # Zero-return benchmark predicts exactly 0 bps; compare MAE on identical outcomes.
            errors.append({"abs_error_bps": abs(signed_error), "signed_error_bps": signed_error,
                "baseline_abs_error_bps": abs(actual_change_bps),
                "direction_correct": (actual_change_bps > 0) == (predicted_bps > 0) if predicted_bps != 0 and actual_change_bps != 0 else None,
                "actual_change_bps": actual_change_bps, "predicted_change_bps": predicted_bps,
                "target_gap_seconds": target_gap, "target_timestamp": target_at,
                "evaluated_price_timestamp": closest["timestamp"],
                "volatility_regime": old.get("volatility_regime", "UNKNOWN")})
        if now - LAST_FORECAST_AT[horizon_seconds] >= 10:
            forecasts.append({"issued_at": now, "reference_price": mid, "predicted_change_bps": forecast_bps,
                              "volatility_regime": volatility_regime})
            LAST_FORECAST_AT[horizon_seconds] = now
        directional = [x for x in errors if x["direction_correct"] is not None]
        regime_evaluation = {}
        for regime in ("LOW", "NORMAL", "HIGH"):
            subset = [x for x in errors if x.get("volatility_regime") == regime]
            sub_mae = sum(x["abs_error_bps"] for x in subset)/len(subset) if subset else None
            sub_baseline = sum(x["baseline_abs_error_bps"] for x in subset)/len(subset) if subset else None
            sub_directional = [x for x in subset if x["direction_correct"] is not None]
            regime_evaluation[regime] = {"matured_forecasts": len(subset),
                "mean_absolute_error_bps": sub_mae,
                "zero_return_baseline_mae_bps": sub_baseline,
                "mae_improvement_vs_zero_baseline_pct": (100.0*(sub_baseline-sub_mae)/sub_baseline) if sub_mae is not None and sub_baseline is not None and sub_baseline > 0 else None,
                "directional_accuracy_pct": 100.0*sum(1 for x in sub_directional if x["direction_correct"])/len(sub_directional) if sub_directional else None}
        model_mae = sum(x["abs_error_bps"] for x in errors)/len(errors) if errors else None
        baseline_mae = sum(x["baseline_abs_error_bps"] for x in errors)/len(errors) if errors else None
        result["evaluation"] = {"matured_forecasts": len(errors),
            "pending_forecasts": len(forecasts), "missed_target_snapshots": EVAL_MISSED[horizon_seconds],
            "target_tolerance_seconds": FORECAST_TARGET_TOLERANCE_SECONDS,
            "mean_absolute_error_bps": model_mae,
            "zero_return_baseline_mae_bps": baseline_mae,
            "mae_improvement_vs_zero_baseline_pct": (100.0 * (baseline_mae-model_mae) / baseline_mae) if model_mae is not None and baseline_mae is not None and baseline_mae > 0 else None,
            "directional_accuracy_pct": 100.0*sum(1 for x in directional if x["direction_correct"])/len(directional) if directional else None,
            "directional_scored_forecasts": len(directional),
            "volatility_regime": volatility_regime,
            "regime_thresholds_median_abs_1m_bps": {"LOW_MAX": 2.0, "NORMAL_MAX": 8.0, "HIGH_MIN": 8.0},
            "by_volatility_regime": regime_evaluation,
            "mean_target_gap_seconds": sum(x["target_gap_seconds"] for x in errors)/len(errors) if errors else None,
            "last_evaluated_error_bps": errors[-1]["signed_error_bps"] if errors else None,
            "evaluation_method": "closest RAM mid-price within ±3s of exact forecast target; zero-return benchmark; mid-to-mid not fill/P&L"}
    return result


def summarize_book_dynamics(now, snapshots):
    """Summarize recent Level-2 changes from the bounded RAM-only event buffer."""
    if not snapshots:
        return {"snapshots": 0, "available": False}
    current = snapshots[-1]
    result = {"snapshots": len(snapshots), "available": True}
    for seconds in (5, 15, 30, 60):
        cutoff = now - seconds
        old = next((x for x in reversed(snapshots) if x["timestamp"] <= cutoff), None)
        if old is None:
            result[str(seconds)] = {"available": False}
            continue
        row = {}
        for key in ("imbalance_5", "imbalance_10"):
            row[key + "_change"] = num(current.get(key)) - num(old.get(key))
        for key in ("bid_depth_5", "ask_depth_5", "bid_depth_10", "ask_depth_10"):
            before, after = num(old.get(key)), num(current.get(key))
            row[key + "_change_pct"] = ((after / before) - 1.0) * 100.0 if before > 0 else None
        mid = num(current.get("mid_price"))
        row["spread_change_bps"] = ((num(current.get("spread")) - num(old.get("spread"))) / mid * 10000.0) if mid > 0 else None
        row["available"] = True
        result[str(seconds)] = row
    return result


def analyze_price_action(candle_frames, book, windows):
    """Descriptive market-structure/liquidity context. Never emits an entry signal."""
    rows = candle_frames.get("1m", [])[-100:]
    if len(rows) < 10:
        return {"status": "INSUFFICIENT_HISTORY", "structure": "UNKNOWN",
                "regime": "UNKNOWN", "sweep": "NONE", "support": None,
                "resistance": None, "atr_bps": None,
                "interpretation": "Waiting for more 1m candles."}

    def val(row, key):
        return num(row.get(key))

    # Confirmed two-bar fractal pivots; last two bars are excluded to avoid look-ahead.
    highs, lows = [], []
    for i in range(2, len(rows) - 2):
        hi, lo = val(rows[i], "high"), val(rows[i], "low")
        if hi > 0 and all(hi > val(rows[j], "high") for j in (i-2, i-1, i+1, i+2)):
            highs.append((i, hi))
        if lo > 0 and all(lo < val(rows[j], "low") for j in (i-2, i-1, i+1, i+2)):
            lows.append((i, lo))
    structure = "MIXED"
    if len(highs) >= 2 and len(lows) >= 2:
        hh, ph = highs[-1][1], highs[-2][1]
        hl, pl = lows[-1][1], lows[-2][1]
        if hh > ph and hl > pl:
            structure = "HIGHER_HIGHS_HIGHER_LOWS"
        elif hh < ph and hl < pl:
            structure = "LOWER_HIGHS_LOWER_LOWS"

    last = rows[-1]
    close, high, low = val(last, "close"), val(last, "high"), val(last, "low")
    prior_high = highs[-1][1] if highs else None
    prior_low = lows[-1][1] if lows else None
    sweep = "NONE"
    if prior_high is not None and high > prior_high and close < prior_high:
        sweep = "UPWARD_SWEEP_REJECTED"
    elif prior_low is not None and low < prior_low and close > prior_low:
        sweep = "DOWNWARD_SWEEP_RECLAIMED"

    tr = []
    for i in range(max(1, len(rows)-15), len(rows)):
        prev_close = val(rows[i-1], "close")
        h, l = val(rows[i], "high"), val(rows[i], "low")
        if prev_close > 0 and h > 0 and l > 0:
            tr.append(max(h-l, abs(h-prev_close), abs(l-prev_close)))
    atr = sum(tr) / len(tr) if tr else 0.0
    atr_bps = atr / close * 10000 if close > 0 else 0.0
    closes = [val(r, "close") for r in rows[-6:]]
    move_bps = (closes[-1]/closes[0]-1)*10000 if len(closes) >= 2 and closes[0] > 0 else 0.0
    if atr_bps >= 25:
        volatility = "HIGH_VOLATILITY"
    elif atr_bps <= 6:
        volatility = "LOW_VOLATILITY"
    else:
        volatility = "NORMAL_VOLATILITY"
    regime = ("TRENDING_UP" if move_bps > max(atr_bps*1.5, 0.1) else
              "TRENDING_DOWN" if move_bps < -max(atr_bps*1.5, 0.1) else "ROTATIONAL_OR_MIXED")
    if volatility == "HIGH_VOLATILITY":
        regime += "_HIGH_VOL"
    flow = windows.get("30", {})
    total = num(flow.get("buy_volume")) + num(flow.get("sell_volume"))
    flow_delta_pct = num(flow.get("delta")) / total if total > 0 else 0.0
    imbalance = num(book.get("imbalance_5"))
    support = prior_low
    resistance = prior_high
    interpretation = "Structure is mixed; wait for a confirmed break or rejection."
    if sweep == "UPWARD_SWEEP_REJECTED":
        interpretation = "Price breached a confirmed swing high then closed back below it; watch follow-through, not the sweep alone."
    elif sweep == "DOWNWARD_SWEEP_RECLAIMED":
        interpretation = "Price breached a confirmed swing low then closed back above it; watch follow-through, not the sweep alone."
    elif structure == "HIGHER_HIGHS_HIGHER_LOWS":
        interpretation = "Swing structure is rising; a loss of the latest confirmed swing low would weaken this context."
    elif structure == "LOWER_HIGHS_LOWER_LOWS":
        interpretation = "Swing structure is falling; a reclaim of the latest confirmed swing high would weaken this context."
    return {
        "status": "OK", "structure": structure, "regime": regime,
        "volatility_regime": volatility, "sweep": sweep,
        "last_close": close, "support": support, "resistance": resistance,
        "atr_bps": round(atr_bps, 3), "last_5bar_move_bps": round(move_bps, 3),
        "book_imbalance_l5": round(imbalance, 4),
        "aggressive_flow_delta_30s": round(num(flow.get("delta")), 4),
        "aggressive_flow_normalized_30s": round(flow_delta_pct, 4),
        "interpretation": interpretation,
        "method": "confirmed 2-bar fractal pivots + 1m true-range regime + 30s flow/book context",
        "is_trade_signal": False
    }



def advanced_price_action(candle_frames):
    """Multi-timeframe structure map; descriptive only, never an order signal."""
    def v(row, key):
        return num(row.get(key))

    def pivots(rows):
        highs, lows = [], []
        for i in range(2, len(rows)-2):
            h, l = v(rows[i], "high"), v(rows[i], "low")
            if h > 0 and all(h > v(rows[j], "high") for j in (i-2,i-1,i+1,i+2)):
                highs.append((i,h))
            if l > 0 and all(l < v(rows[j], "low") for j in (i-2,i-1,i+1,i+2)):
                lows.append((i,l))
        return highs, lows

    def tf_bias(tf):
        data = candle_frames.get(tf, [])
        if len(data) < 12:
            return {"status":"INSUFFICIENT_HISTORY","bias":"UNKNOWN","structure":"UNKNOWN"}
        hh, ll = pivots(data[-180:])
        structure = "MIXED"
        if len(hh)>=2 and len(ll)>=2:
            if hh[-1][1]>hh[-2][1] and ll[-1][1]>ll[-2][1]: structure="HH_HL"
            elif hh[-1][1]<hh[-2][1] and ll[-1][1]<ll[-2][1]: structure="LH_LL"
        return {"status":"OK","bias":"BULLISH" if structure=="HH_HL" else "BEARISH" if structure=="LH_LL" else "NEUTRAL",
                "structure":structure,"close":v(data[-1],"close"),"bars":len(data),
                "swing_high":hh[-1][1] if hh else None,"swing_low":ll[-1][1] if ll else None}

    rows = candle_frames.get("1m", [])[-180:]
    higher = {tf:tf_bias(tf) for tf in ("1d","4h","1h","15m")}
    if len(rows)<20:
        return {"status":"INSUFFICIENT_HISTORY","higher_timeframe":higher,"is_trade_signal":False}
    highs,lows = pivots(rows)
    close,last = v(rows[-1],"close"),rows[-1]

    # Swing speed compares last pivot-to-pivot up/down legs, normalized to bps per bar.
    legs=[]
    for (ia,pa,ta),(ib,pb,tb) in zip(
        sorted([(i,p,"H") for i,p in highs]+[(i,p,"L") for i,p in lows]),
        sorted([(i,p,"H") for i,p in highs]+[(i,p,"L") for i,p in lows])[1:]):
        if ta==tb or ib<=ia or pa<=0 or pb<=0: continue
        move=(pb/pa-1)*10000
        legs.append({"dir":"UP" if move>0 else "DOWN","speed":abs(move)/(ib-ia),
                     "bars":ib-ia,"move":abs(move)})
    ups=[x for x in legs if x["dir"]=="UP"]; downs=[x for x in legs if x["dir"]=="DOWN"]
    momentum={"status":"INSUFFICIENT_SWINGS"}
    if ups and downs:
        up,dn=ups[-1],downs[-1]; ratio=up["speed"]/max(dn["speed"],1e-9)
        momentum={"status":"OK","comparison":"BUYER_LEG_STRONGER" if ratio>1.25 and up["bars"]<=dn["bars"] else
                  "SELLER_LEG_STRONGER" if ratio<0.8 and dn["bars"]<=up["bars"] else "MIXED_MOMENTUM",
                  "up_speed_bps_per_bar":round(up["speed"],4),"down_speed_bps_per_bar":round(dn["speed"],4),
                  "up_vs_down_speed_ratio":round(ratio,3),"up_bars":up["bars"],"down_bars":dn["bars"]}

    # MSS only when a protected pivot breaks with >=1.2x recent volume; otherwise no MSS.
    protected_low=next((p for i,p in reversed(lows) if highs and i<highs[-1][0]),None)
    protected_high=next((p for i,p in reversed(highs) if lows and i<lows[-1][0]),None)
    vols=[v(r,"volume") for r in rows[-21:-1]]
    meanvol=sum(vols)/len(vols) if vols else 0
    volratio=v(last,"volume")/meanvol if meanvol>0 else None
    mss="NONE"
    if protected_low and close<protected_low and volratio is not None and volratio>=1.2: mss="BEARISH_MSS_WITH_VOLUME"
    elif protected_high and close>protected_high and volratio is not None and volratio>=1.2: mss="BULLISH_MSS_WITH_VOLUME"

    # Cluster swing pivots into approximate support/resistance reaction bands.
    points=[(p,"RESISTANCE") for _,p in highs[-18:]]+[(p,"SUPPORT") for _,p in lows[-18:]]
    clusters=[]
    for price,kind in sorted(points):
        match=next((z for z in clusters if z["type"]==kind and abs(z["mid"]-price)<=price*0.0015),None)
        if match: match["values"].append(price); match["mid"]=sum(match["values"])/len(match["values"])
        else: clusters.append({"type":kind,"mid":price,"values":[price]})
    ssr=[{"type":z["type"],"low":round(min(z["values"]),2),"high":round(max(z["values"]),2),
          "mid":round(z["mid"],2),"touches":len(z["values"]),
          "distance_bps":round((z["mid"]/close-1)*10000,2)}
         for z in clusters if close>0]
    ssr=sorted(ssr,key=lambda z:abs(z["distance_bps"]))[:8]

    # Approximate displacement-origin zones, explicitly not proof of institutional orders.
    trs=[]
    for i in range(1,len(rows)):
        pc,h,l=v(rows[i-1],"close"),v(rows[i],"high"),v(rows[i],"low")
        if pc>0: trs.append(max(h-l,abs(h-pc),abs(l-pc)))
    atr=sum(trs[-20:])/len(trs[-20:]) if trs else 0
    avgvol=sum(vols)/len(vols) if vols else 0
    zones=[]
    for i in range(max(3,len(rows)-45),len(rows)-1):
        r=rows[i]; body=abs(v(r,"close")-v(r,"open")); rv=v(r,"volume")
        if atr<=0 or body<1.5*atr or (avgvol>0 and rv<1.25*avgvol): continue
        base=rows[max(0,i-3):i]
        zl=min(v(x,"low") for x in base); zh=max(v(x,"high") for x in base)
        fresh=not any(v(x,"low")<=zh and v(x,"high")>=zl for x in rows[i+1:])
        zones.append({"type":"DEMAND" if v(r,"close")>v(r,"open") else "SUPPLY",
                      "low":round(zl,2),"high":round(zh,2),"fresh":fresh,
                      "origin_timestamp":r.get("timestamp"),
                      "displacement_bps":round(body/max(v(r,"close"),1e-9)*10000,2),
                      "volume_ratio":round(rv/avgvol,2) if avgvol>0 else None})
    zones=zones[-6:]

    # Basic breakout state and 15m rejection/engulfing context.
    ph=highs[-1][1] if highs else None; pl=lows[-1][1] if lows else None
    retest="NONE"
    prior_bars=rows[-8:-1]
    prior_bull_break=bool(ph and any(v(r,"close")>ph for r in prior_bars))
    prior_bear_break=bool(pl and any(v(r,"close")<pl for r in prior_bars))
    if ph and prior_bull_break and v(last,"low")<=ph*1.0015 and close>ph:
        retest="BULLISH_RETEST_HOLD"
    elif pl and prior_bear_break and v(last,"high")>=pl*0.9985 and close<pl:
        retest="BEARISH_RETEST_HOLD"
    elif ph and close>ph: retest="BREAKOUT_ABOVE_SWING_HIGH"
    elif pl and close<pl: retest="BREAKDOWN_BELOW_SWING_LOW"
    f15=candle_frames.get("15m",[]); confirmation="UNAVAILABLE"
    if f15:
        confirmation="NO_CLEAR_PATTERN"
        c=f15[-1]; o,h,l,cl=(v(c,k) for k in ("open","high","low","close")); rng=max(h-l,1e-9)
        prev=f15[-2] if len(f15)>1 else None
        if (min(o,cl)-l)/rng>0.55 and cl>=o: confirmation="15M_BULLISH_REJECTION"
        elif (h-max(o,cl))/rng>0.55 and cl<=o: confirmation="15M_BEARISH_REJECTION"
        elif prev and cl>o and cl>v(prev,"open") and o<v(prev,"close"): confirmation="15M_BULLISH_ENGULFING_CANDIDATE"
        elif prev and cl<o and cl<v(prev,"open") and o>v(prev,"close"): confirmation="15M_BEARISH_ENGULFING_CANDIDATE"
        elif prev and h<v(prev,"high") and l>v(prev,"low"): confirmation="15M_INSIDE_BAR"

    biases=[higher[t]["bias"] for t in ("1d","4h","1h") if higher[t]["status"]=="OK"]
    topdown="ALIGNED_BULLISH" if len(biases)>=2 and all(x=="BULLISH" for x in biases) else (
            "ALIGNED_BEARISH" if len(biases)>=2 and all(x=="BEARISH" for x in biases) else
            "TIMEFRAME_CONFLICT" if "BULLISH" in biases and "BEARISH" in biases else "MIXED_OR_INCOMPLETE")
    return {"status":"OK","higher_timeframe":higher,"top_down_bias":topdown,
            "swing_momentum":momentum,"market_structure_shift":mss,
            "protected_swing_low":protected_low,"protected_swing_high":protected_high,
            "volume_vs_20bar_mean":round(volratio,3) if volratio is not None else None,
            "support_resistance_zones":ssr,"supply_demand_zones":zones,
            "breakout_retest_state":retest,"15m_candle_confirmation":confirmation,
            "latest_close":close,"is_trade_signal":False,
            "interpretation":"Structure/zone approximations only; public candles cannot reveal actual institutional positions or prove where institutions are holding orders."}


def make_state():
    now = time.time()
    with LOCK:
        snapshot_mid = (num(FEED["book"].get("mid_price")) or
                       num(FEED["market"].get("mid_price")) or
                       num(FEED["market"].get("last_price")))
        # Sample only live mid/last price into a bounded in-memory ring buffer.
        # No price snapshots or evaluation records are persisted to device storage.
        if snapshot_mid > 0 and (not PRICE_HISTORY or now - PRICE_HISTORY[-1]["timestamp"] >= 1.0):
            PRICE_HISTORY.append({"timestamp": now, "mid_price": snapshot_mid})
        market = dict(FEED["market"])
        book = dict(FEED["book"])
        # Only the last 60 seconds are needed for live flow windows. Avoid copying/scanning
        # the entire 5,000-trade ring on every state publication.
        trade_count = len(TRADES)
        trades = []
        for trade in reversed(TRADES):
            age = now - trade["timestamp"]
            if age > 60.0:
                break
            if age >= 0.0:
                trades.append(trade)
        trades.reverse()
        book_history = list(BOOK_HISTORY)
        candle_frames = {tf: list(frame) for tf, frame in CANDLES_BY_TF.items()}
        candle_fetched_at = dict(CANDLE_FETCHED_AT)
        candles = candle_frames["1m"]
        connected = bool(FEED["connected"])
        channel_seen = dict(FEED["channel_seen"])
        last_message = FEED["last_message_at"]
        last_error = FEED["last_error"]
        mark = FEED["mark_price"]
        funding = dict(FEED["funding"])
        cvd = FEED["cvd_since_start"]
        connection_state = FEED["connection_state"]
    windows = {}
    for seconds in (1, 5, 30, 60):
        sample = [t for t in trades if 0 <= now - t["timestamp"] <= seconds]
        buy = sum(t["size"] for t in sample if t["side"] == "buy")
        sell = sum(t["size"] for t in sample if t["side"] == "sell")
        total = buy + sell
        windows[str(seconds)] = {"buy_volume": buy, "sell_volume": sell, "delta": buy - sell,
                                 "delta_pct": (buy - sell) / total if total else 0.0, "samples": len(sample)}
    latest_trade_age = max(0.0, now - trades[-1]["timestamp"]) if trades else None
    latest_book_age = max(0.0, now - num(book.get("updated_at"), 0)) if book else None
    book_dynamics = summarize_book_dynamics(now, book_history)
    valid_l2 = (num(book.get("best_bid")) > 0 and
                num(book.get("best_ask")) > num(book.get("best_bid")) and
                num(book.get("mid_price")) > 0)
    book_fresh = latest_book_age is not None and latest_book_age <= 3.0
    stale = not connected or last_message is None or now - last_message > 6 or not valid_l2 or not book_fresh
    imbalance = num(book.get("imbalance_5"))
    micro = {
        "symbol": SYMBOL, "timestamp": now, "updated_at_epoch": last_message,
        "order_book": book, "windows": windows, "cvd": cvd,
        "book_dynamics": book_dynamics,
        "cvd_slope_30s": windows["30"]["delta"],
        "quality": {"fresh_seconds": max(0.0, now - last_message) if last_message else None,
                    "trade_samples": trade_count, "recent_trade_samples": len(trades), "book_samples": len(book.get("bids_l5", [])) if book else 0,
                    "connection_state": connection_state, "connected": connected,
                    "latest_trade_age_s": latest_trade_age, "latest_book_age_s": latest_book_age,
                    "last_error": last_error},
        "regime": None,
    }
    market.setdefault("symbol", SYMBOL)
    market["connection_state"] = connection_state
    market["connected"] = connected
    # Do not calculate or present a live forecast from a stale/invalid depth snapshot.
    feed_fresh = not stale
    forecast = build_five_minute_forecast(now, market, book, trades, candle_frames, windows, mark, funding, feed_fresh, 300, book_dynamics)
    forecast_10m = build_five_minute_forecast(now, market, book, trades, candle_frames, windows, mark, funding, feed_fresh, 600, book_dynamics)
    market_behavior = analyze_price_action(candle_frames, book, windows) if feed_fresh else {
        "status": "STALE_FEED", "structure": "UNKNOWN", "regime": "PAUSED",
        "sweep": "UNKNOWN", "support": None, "resistance": None, "atr_bps": None,
        "interpretation": "Live feed stale or disconnected; market-behaviour analysis paused.",
        "is_trade_signal": False
    }
    advanced_context = advanced_price_action(candle_frames) if feed_fresh else {
        "status": "STALE_FEED", "is_trade_signal": False,
        "interpretation": "Live feed stale; advanced price-action context paused."
    }
    instrument = {"venue": "Delta Exchange India", "symbol": SYMBOL, "contract_type": "perpetual_futures",
                  "underlying": "BTC", "verified": True,
                  "checks": {"configured_symbol_is_btcusd": True, "public_india_endpoint": True},
                  "reason": "", "candle_symbol": SYMBOL, "candle_source": "Delta public candle REST + WebSocket",
                  "data_is_live": not stale, "channels": {k: round(now-v, 2) for k, v in channel_seen.items()}}
    return {"read_only": True, "persistence": "RAM_ONLY", "instrument": instrument,
            "market": market, "micro": micro, "market_behavior": market_behavior,
            "advanced_context": advanced_context,
            "forecast_5m": forecast, "forecast_10m": forecast_10m,
            "candles": candles[-240:], "candle_count": len(candles),
            "candle_frames": candle_frames,
            "candle_frame_health": {tf: {"count": len(rows),
                "age_s": round(max(0.0, now-candle_fetched_at[tf]), 2) if candle_fetched_at[tf] else None,
                "source": "Delta public candle REST + 1m WebSocket" if tf == "1m" else "Delta public candle REST"}
                for tf, rows in candle_frames.items()},
            "health": {"micro_stale": stale, "connected": connected, "connection_state": connection_state,
                       "last_message_age_s": round(now-last_message, 3) if last_message else None,
                       "latest_trade_age_s": round(latest_trade_age, 3) if latest_trade_age is not None else None,
                       "latest_book_age_s": round(latest_book_age, 3) if latest_book_age is not None else None,
                       "trade_count_in_memory": trade_count, "recent_trade_count_60s": len(trades), "book_snapshots_in_memory": len(book_history),
                       "price_snapshots_in_memory": len(PRICE_HISTORY),
                       "book_rejected_crossed": int(FEED.get("book_rejected_crossed", 0)),
                       "timestamp_missing_count": int(FEED.get("timestamp_missing_count", 0)),
                       "candle_count_in_memory": len(candles),
                       "mark_price": mark, "funding": funding, "last_error": last_error,
                       "snapshot_time": now}}


def state_publisher_worker():
    """Publish cached state at 1 Hz to cap mobile CPU/battery use; market feed stays live."""
    while not STOP.is_set():
        started = time.monotonic()
        try:
            payload = json.dumps(make_state(), separators=(",", ":"), allow_nan=False).encode("utf-8")
            with STATE_CACHE_LOCK:
                STATE_CACHE["json"] = payload
                STATE_CACHE["updated_at"] = time.time()
        except Exception as exc:
            with LOCK:
                FEED["last_error"] = "State publisher: " + type(exc).__name__ + ": " + str(exc)[:140]
        STOP.wait(max(0.1, 1.0 - (time.monotonic() - started)))


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "DeltaBtcReadOnly/2.1"

    def _send(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/api/state":
            with STATE_CACHE_LOCK:
                payload = STATE_CACHE["json"]
            if payload == b"{}":
                payload = json.dumps(make_state(), separators=(",", ":"), allow_nan=False).encode("utf-8")
            return self._send(200, payload, "application/json; charset=utf-8")
        if path in ("/", "/market_visualizer.html"):
            try:
                payload = (WEB / "market_visualizer.html").read_bytes()
            except OSError:
                return self._send(404, b"Dashboard file not found", "text/plain; charset=utf-8")
            return self._send(200, payload, "text/html; charset=utf-8")
        return self._send(404, b"Not found", "text/plain; charset=utf-8")

    def log_message(self, *_args):
        return


if __name__ == "__main__":
    threading.Thread(target=history_worker, name="delta-candle-history", daemon=True).start()
    threading.Thread(target=websocket_worker, name="delta-public-websocket", daemon=True).start()
    threading.Thread(target=state_publisher_worker, name="delta-state-publisher", daemon=True).start()
    print(f"Read-only live Delta BTCUSD perpetual dashboard: http://{HOST}:{PORT}", flush=True)
    print("1Hz RAM state publisher; persistent local HTTP connections; no market data files are written. Ctrl-C to stop.", flush=True)
    try:
        ThreadingHTTPServer((HOST, PORT), Handler).serve_forever(poll_interval=1.0)
    finally:
        STOP.set()
