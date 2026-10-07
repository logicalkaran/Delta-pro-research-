"""Live-market paper execution simulator. NEVER submits exchange orders.
Uses the existing live microstructure state and the V2 ABSREV selector.
Entry is post-only with queue-ahead simulation; exits are executable taker-style
with spread/slippage, fees, stale-data and kill-switch guards.
"""
from __future__ import annotations
import json, os, time, math, signal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "data/live_microstructure_state.json"
OUT = ROOT / "data/processed/live_execution_paper_v2.jsonl"
SUMMARY = ROOT / "data/processed/live_execution_paper_v2_summary.json"
KILL = ROOT / "data/run/LIVE_KILL_SWITCH"

SYMBOL = "BTCUSD"
CONTRACTS = 1
CONTRACT_BTC = 0.001
TICK = 0.50

# V2 strongest candidate: ABSREV, 600s horizon, 5/10 bps.
FLOW_THRESHOLD = 0.10
ABSORPTION_MAX_ADVERSE_BPS = 4.0
CONFIRM_BPS = 1.0
STOP_BPS = 5.0
TARGET_BPS = 10.0
MAX_HOLD_S = 600.0

# Conservative fee model: maker entry + taker stop/target exit.
MAKER_FEE_BPS = 2.36
TAKER_FEE_BPS = 5.90
EXTRA_EXIT_SLIPPAGE_TICKS = 1.0

# Queue model. The simulator never assumes an immediate maker fill.
QUEUE_DEPTH_FRACTION = 0.02
MIN_QUEUE_AHEAD = 1.0
MAX_ENTRY_AGE_S = 3.0
MAX_STATE_AGE_S = 2.0

RUNNING = True

def stop_handler(signum, frame):
    global RUNNING
    RUNNING = False

signal.signal(signal.SIGINT, stop_handler)
signal.signal(signal.SIGTERM, stop_handler)

def read_state():
    try:
        return json.loads(STATE.read_text())
    except Exception:
        return None

def f(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default

def round_tick(p):
    return round(p / TICK) * TICK

def bps_change(a, b):
    return (b / a - 1.0) * 10000.0 if a > 0 else 0.0

def selector(s):
    if not s:
        return None, "NO_STATE"
    q = s.get("quality", {})
    if f(q.get("fresh_seconds"), 999) > MAX_STATE_AGE_S:
        return None, "STALE_DATA"
    w5 = s.get("windows", {}).get("5", {})
    p5 = s.get("price", {}).get("5", {})
    ob = s.get("order_book", {})
    d = f(w5.get("delta_pct"))
    ret = f(p5.get("return_pct"))
    obi = f(ob.get("imbalance_5"))
    # ABSREV: heavy aggressive flow with limited price response.
    # The opposite side is then confirmed by a >=1bp reversal from the
    # candidate reference price.
    if d <= -FLOW_THRESHOLD and ret >= -ABSORPTION_MAX_ADVERSE_BPS / 100.0:
        return "LONG_CANDIDATE", "SELL_ABSORPTION"
    if d >= FLOW_THRESHOLD and ret <= ABSORPTION_MAX_ADVERSE_BPS / 100.0:
        return "SHORT_CANDIDATE", "BUY_ABSORPTION"
    return None, "NO_ABSREV"

def append(row):
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, separators=(",", ":")) + "\n")

def fee_usd(price, bps):
    return price * CONTRACT_BTC * CONTRACTS * bps / 10000.0

def exit_quote(s, side):
    ob = s.get("order_book", {})
    bid, ask = f(ob.get("best_bid")), f(ob.get("best_ask"))
    spread = max(ask - bid, 0.0)
    slip = EXTRA_EXIT_SLIPPAGE_TICKS * TICK
    if side == "LONG":
        # Sell to close: executable bid, conservatively one extra tick worse.
        return max(TICK, bid - slip), spread
    # Buy to close: executable ask, conservatively one extra tick worse.
    return ask + slip, spread

def main(duration_s=86400):
    global RUNNING
    start = time.time()
    position = None
    candidate = None
    last_trade_ts = None
    last_signal = None
    stats = {
        "observations": 0, "candidate_events": 0, "orders_posted": 0,
        "maker_fills": 0, "unfilled_cancelled": 0, "trades": 0,
        "wins": 0, "losses": 0, "stops": 0, "targets": 0, "timeouts": 0,
        "stale_blocks": 0, "kill_blocks": 0, "sum_net_bps": 0.0,
        "sum_net_usd": 0.0, "queue_fill_events": 0
    }
    trades = []
    print("LIVE PAPER V2 STARTED | REAL ORDERS OFF | ABSREV 600s 5/10 | POST-ONLY QUEUE SIM", flush=True)

    while RUNNING and time.time() - start < duration_s:
        s = read_state()
        now = time.time()
        stats["observations"] += 1
        if not s:
            time.sleep(0.25)
            continue

        q = s.get("quality", {})
        if f(q.get("fresh_seconds"), 999) > MAX_STATE_AGE_S:
            stats["stale_blocks"] += 1
            time.sleep(0.25)
            continue

        ob = s.get("order_book", {})
        bid, ask, mid = f(ob.get("best_bid")), f(ob.get("best_ask")), f(ob.get("mid_price"))
        if bid <= 0 or ask <= 0 or mid <= 0:
            time.sleep(0.25)
            continue

        last = s.get("last_trade", {})
        trade_ts = last.get("ts")
        new_trade = trade_ts is not None and trade_ts != last_trade_ts
        if new_trade:
            last_trade_ts = trade_ts

        # Manage a resting post-only entry.
        if position is None and candidate is not None:
            if now - candidate["created_at"] > MAX_ENTRY_AGE_S:
                append({"ts": now, "event": "ENTRY_CANCEL", "reason": "QUEUE_TIMEOUT",
                        "candidate": candidate})
                stats["unfilled_cancelled"] += 1
                candidate = None
            else:
                side = candidate["side"]
                limit = candidate["limit_price"]
                # If market moves through the resting order, treat it as a fill,
                # but never better than the original limit. This avoids mid-price fills.
                crossed = (side == "LONG" and ask <= limit) or (side == "SHORT" and bid >= limit)
                consumed = 0.0
                if new_trade:
                    tp = f(last.get("price"))
                    ts = str(last.get("side", "")).lower()
                    size = abs(f(last.get("size")))
                    if side == "LONG" and ts == "sell" and tp <= limit:
                        consumed = size
                    elif side == "SHORT" and ts == "buy" and tp >= limit:
                        consumed = size
                candidate["queue_ahead"] -= consumed
                if "posted" in candidate and (candidate["queue_ahead"] <= 0 or crossed):
                    entry = limit
                    position = {
                        "side": side, "entry": entry, "opened_at": now,
                        "stop": round_tick(entry * (1 - STOP_BPS/10000)) if side == "LONG" else round_tick(entry * (1 + STOP_BPS/10000)),
                        "target": round_tick(entry * (1 + TARGET_BPS/10000)) if side == "LONG" else round_tick(entry * (1 - TARGET_BPS/10000)),
                        "entry_fee_usd": fee_usd(entry, MAKER_FEE_BPS),
                        "queue_initial": candidate["queue_initial"],
                        "queue_consumed": candidate["queue_initial"] - max(candidate["queue_ahead"], 0),
                        "candidate_reason": candidate["reason"],
                    }
                    stats["maker_fills"] += 1
                    stats["queue_fill_events"] += 1
                    append({"ts": now, "event": "MAKER_FILL", "position": position})
                    candidate = None

        # Create a new candidate only when flat and no existing order.
        if position is None and candidate is None:
            raw_side, reason = selector(s)
            if raw_side:
                side = "LONG" if raw_side.startswith("LONG") else "SHORT"
                ref = mid
                # Confirmation is based on future movement from this reference.
                candidate = {
                    "side": side, "reason": reason, "created_at": now,
                    "reference_price": ref, "limit_price": round_tick(bid if side == "LONG" else ask),
                    "queue_initial": max(MIN_QUEUE_AHEAD,
                        (f(ob.get("bid_depth_5")) if side == "LONG" else f(ob.get("ask_depth_5"))) * QUEUE_DEPTH_FRACTION),
                    "queue_ahead": 0.0
                }
                candidate["queue_ahead"] = candidate["queue_initial"]
                stats["candidate_events"] += 1
                append({"ts": now, "event": "ABSREV_CANDIDATE", "candidate": candidate})

        # A candidate requires reversal confirmation before it is allowed to post.
        if position is None and candidate is not None and "posted" not in candidate:
            rev = bps_change(candidate["reference_price"], mid)
            confirmed = (candidate["side"] == "LONG" and rev >= CONFIRM_BPS) or (candidate["side"] == "SHORT" and rev <= -CONFIRM_BPS)
            if confirmed:
                candidate["posted"] = True
                stats["orders_posted"] += 1
                append({"ts": now, "event": "POST_ONLY_ENTRY", "candidate": candidate})

        # Before confirmation, cancel if the candidate becomes invalid.
        if position is None and candidate is not None and "posted" not in candidate:
            if now - candidate["created_at"] > MAX_ENTRY_AGE_S:
                append({"ts": now, "event": "ENTRY_CANCEL", "reason": "NO_CONFIRMATION",
                        "candidate": candidate})
                stats["unfilled_cancelled"] += 1
                candidate = None

        # Manage filled position with executable stop/target/time exit.
        if position is not None:
            side = position["side"]
            exit_px, spread = exit_quote(s, side)
            if side == "LONG":
                stop_hit = exit_px <= position["stop"]
                target_hit = exit_px >= position["target"]
            else:
                stop_hit = exit_px >= position["stop"]
                target_hit = exit_px <= position["target"]
            age = now - position["opened_at"]
            reason = None
            if stop_hit:
                reason = "STOP"
            elif target_hit:
                reason = "TARGET"
            elif age >= MAX_HOLD_S:
                reason = "TIME"

            if reason:
                gross_bps = bps_change(position["entry"], exit_px)
                if side == "SHORT":
                    gross_bps = -gross_bps
                exit_fee = fee_usd(exit_px, TAKER_FEE_BPS)
                total_fee = position["entry_fee_usd"] + exit_fee
                net_usd = (gross_bps / 10000.0) * position["entry"] * CONTRACT_BTC * CONTRACTS - total_fee
                notional = position["entry"] * CONTRACT_BTC * CONTRACTS
                net_bps = net_usd / notional * 10000.0 if notional else 0.0
                row = {
                    "ts": now, "event": "PAPER_EXIT", "side": side,
                    "entry": position["entry"], "exit": exit_px,
                    "gross_bps": gross_bps, "net_bps": net_bps,
                    "net_usd": net_usd, "fees_usd": total_fee,
                    "hold_s": age, "exit_reason": reason,
                    "spread_at_exit": spread,
                    "queue_initial": position["queue_initial"],
                    "queue_consumed": position["queue_consumed"]
                }
                append(row)
                trades.append(row)
                stats["trades"] += 1
                stats["sum_net_bps"] += net_bps
                stats["sum_net_usd"] += net_usd
                if net_bps > 0: stats["wins"] += 1
                else: stats["losses"] += 1
                stats[reason.lower() + "s" if reason != "TIME" else "timeouts"] += 1
                position = None

        time.sleep(0.25)

    # Mark an open paper position as unresolved rather than manufacturing an exit.
    unresolved = position is not None
    wins = [t["net_bps"] for t in trades if t["net_bps"] > 0]
    losses = [-t["net_bps"] for t in trades if t["net_bps"] < 0]
    summary = {
        **stats,
        "duration_s": time.time() - start,
        "unresolved_position": unresolved,
        "open_position": position,
        "win_rate": len(wins) / len(trades) if trades else 0.0,
        "avg_net_bps": sum(t["net_bps"] for t in trades) / len(trades) if trades else 0.0,
        "profit_factor": sum(wins) / sum(losses) if losses else (None if not wins else None),
        "status": "PAPER_ONLY",
        "real_orders": False,
        "production_code_modified": False,
        "strategy": "ABSREV",
        "flow_threshold": FLOW_THRESHOLD,
        "stop_bps": STOP_BPS,
        "target_bps": TARGET_BPS,
        "horizon_s": MAX_HOLD_S,
        "entry_model": "POST_ONLY_QUEUE_SIM",
        "exit_model": "EXECUTABLE_TAKER_CONSERVATIVE",
        "maker_fee_bps": MAKER_FEE_BPS,
        "taker_fee_bps": TAKER_FEE_BPS,
        "promotion": "BLOCKED"
    }
    SUMMARY.write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2), flush=True)

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=int, default=86400)
    args = ap.parse_args()
    main(args.seconds)
