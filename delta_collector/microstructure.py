"""Read-only short-term BTC microstructure analytics.

Consumes Delta trades, L1 and L2 events and publishes normalized
volume-delta/order-book/price-behaviour state. It never creates orders.
"""
from __future__ import annotations

import json
import math
import os
import time
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "live_microstructure_state.json"

WINDOWS = (5, 30, 60)
MAX_TRADES = 5000
MAX_PRICES = 3000

_trades = deque(maxlen=MAX_TRADES)
_prices = deque(maxlen=MAX_PRICES)
_book = {"bids": {}, "asks": {}, "ts": None}
_last_l1 = {}
_last_update = 0.0


def _num(value, default=0.0):
    try:
        x = float(value)
        return x if math.isfinite(x) else default
    except (TypeError, ValueError):
        return default


def _depth(levels, n):
    return sum(_num(size) for _, size in levels[:n])


def _imbalance(bid_depth, ask_depth):
    total = bid_depth + ask_depth
    return (bid_depth - ask_depth) / total if total > 0 else 0.0


def _now_us():
    return int(time.time() * 1_000_000)


def _event_ts(message):
    return int(_num(message.get("t") or message.get("ts"), _now_us()))


def _classify_trade(message):
    price = _num(message.get("p"))
    size = abs(_num(message.get("s")))
    bid = _num(_last_l1.get("bp"), 0.0)
    ask = _num(_last_l1.get("ap"), 0.0)
    if size <= 0 or price <= 0:
        return None
    if ask > 0 and price >= ask:
        return 1.0, "buy"
    if bid > 0 and price <= bid:
        return -1.0, "sell"
    # Delta's role field is retained only as a fallback when trade price
    # is between the latest quote. Existing project convention: m=sell.
    if message.get("r") == "m":
        return -1.0, "sell"
    if message.get("r") == "t":
        return 1.0, "buy"
    return 0.0, "unknown"


def _snapshot_l2(message):
    bids = {}
    asks = {}
    for price, size in message.get("b", []):
        q = _num(size)
        if q > 0:
            bids[_num(price)] = q
    for price, size in message.get("a", []):
        q = _num(size)
        if q > 0:
            asks[_num(price)] = q
    _book["bids"] = bids
    _book["asks"] = asks
    _book["ts"] = _event_ts(message)


def _window_stats(now_us, seconds):
    cutoff = now_us - seconds * 1_000_000
    selected = [x for x in _trades if x["ts"] >= cutoff]
    buy = sum(x["size"] for x in selected if x["side"] == "buy")
    sell = sum(x["size"] for x in selected if x["side"] == "sell")
    total = buy + sell
    delta = buy - sell
    return {
        "seconds": seconds,
        "trades": len(selected),
        "buy_volume": round(buy, 6),
        "sell_volume": round(sell, 6),
        "total_volume": round(total, 6),
        "delta": round(delta, 6),
        "delta_pct": round(delta / total if total else 0.0, 6),
        "avg_trade_size": round(total / len(selected), 6) if selected else 0.0,
        "buy_count": sum(x["side"] == "buy" for x in selected),
        "sell_count": sum(x["side"] == "sell" for x in selected),
    }


def _price_stats(now_us):
    current = _prices[-1]["price"] if _prices else None
    result = {}
    for seconds in WINDOWS:
        cutoff = now_us - seconds * 1_000_000
        old = next((x for x in _prices if x["ts"] >= cutoff), None)
        ret = 0.0
        if old and current and old["price"]:
            ret = current / old["price"] - 1.0
        result[str(seconds)] = {
            "seconds": seconds,
            "return": round(ret, 8),
            "return_pct": round(ret * 100.0, 5),
        }
    return result


def _book_stats():
    bids = sorted(_book["bids"].items(), key=lambda x: x[0], reverse=True)
    asks = sorted(_book["asks"].items(), key=lambda x: x[0])
    best_bid = bids[0][0] if bids else _num(_last_l1.get("bp"), 0.0)
    best_ask = asks[0][0] if asks else _num(_last_l1.get("ap"), 0.0)
    mid = (best_bid + best_ask) / 2.0 if best_bid > 0 and best_ask > 0 else 0.0
    spread = best_ask - best_bid if best_bid > 0 and best_ask > 0 else 0.0
    if not bids and not asks:
        d5 = (_num(_last_l1.get("bs"), 0.0), _num(_last_l1.get("as"), 0.0))
        d10 = d5
    else:
        d5 = (_depth(bids, 5), _depth(asks, 5))
        d10 = (_depth(bids, 10), _depth(asks, 10))
    return {
        "best_bid": best_bid,
        "best_ask": best_ask,
        "mid_price": mid,
        "spread": spread,
        "bid_depth_5": d5[0],
        "ask_depth_5": d5[1],
        "imbalance_5": round(_imbalance(*d5), 6),
        "bid_depth_10": d10[0],
        "ask_depth_10": d10[1],
        "imbalance_10": round(_imbalance(*d10), 6),
        "bid_levels": len(bids),
        "ask_levels": len(asks),
    }


def _regime(w5, w30, book, prices):
    p5 = prices["5"]["return_pct"]
    d5 = w5["delta_pct"]
    obi = book["imbalance_5"]
    # These are descriptive regimes, not trade orders.
    if d5 >= 0.20 and p5 > 0 and obi >= 0:
        return "BUYER_CONFIRMATION"
    if d5 <= -0.20 and p5 < 0 and obi <= 0:
        return "SELLER_CONFIRMATION"
    if d5 >= 0.20 and abs(p5) < 0.03 and book["ask_depth_5"] > book["bid_depth_5"]:
        return "BUYER_ABSORPTION"
    if d5 <= -0.20 and abs(p5) < 0.03 and book["bid_depth_5"] > book["ask_depth_5"]:
        return "SELLER_ABSORPTION"
    if abs(d5) < 0.08 and abs(obi) < 0.10:
        return "BALANCED"
    if d5 > 0:
        return "BUY_PRESSURE"
    if d5 < 0:
        return "SELL_PRESSURE"
    return "NEUTRAL"


def _state():
    now_us = _now_us()
    w = {str(s): _window_stats(now_us, s) for s in WINDOWS}
    book = _book_stats()
    prices = _price_stats(now_us)
    w5, w30 = w["5"], w["30"]
    # CVD is maintained from retained classified trades; it is explicitly
    # a rolling observation here, not a signal routed into execution.
    cvd = sum(x["delta"] for x in _trades)
    state = {
        "timestamp": int(time.time()),
        "updated_at_epoch": time.time(),
        "symbol": "BTCUSD",
        "read_only": True,
        "windows": w,
        "price": prices,
        "order_book": book,
        "cvd": round(cvd, 6),
        "cvd_slope_30s": round(w30["delta"], 6),
        "regime": _regime(w5, w30, book, prices),
        "last_trade": _trades[-1] if _trades else None,
        "quality": {
            "trade_samples": len(_trades),
            "book_samples": 1 if _book["ts"] else 0,
            "fresh_seconds": round(max(0.0, time.time() - _last_update), 3) if _last_update else None,
        },
    }
    return state


def _write(state):
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, OUT)


def update(message):
    global _last_l1, _last_update
    if not isinstance(message, dict):
        return
    typ = message.get("type")
    if typ == "ob_l1":
        _last_l1 = {
            "bp": message.get("bp"),
            "bs": message.get("bs"),
            "ap": message.get("ap"),
            "as": message.get("as"),
        }
    elif typ == "ob_l2":
        _snapshot_l2(message)
    elif typ == "trades":
        classified = _classify_trade(message)
        if classified is not None:
            sign, side = classified
            ts = _event_ts(message)
            size = abs(_num(message.get("s")))
            price = _num(message.get("p"))
            _trades.append({
                "ts": ts,
                "price": price,
                "size": size,
                "side": side,
                "delta": sign * size,
            })
            _prices.append({"ts": ts, "price": price})
    else:
        return
    _last_update = time.time()
    _write(_state())


def reset():
    global _last_l1, _last_update
    _trades.clear()
    _prices.clear()
    _book["bids"].clear()
    _book["asks"].clear()
    _book["ts"] = None
    _last_l1 = {}
    _last_update = 0.0
    if OUT.exists():
        OUT.unlink()
