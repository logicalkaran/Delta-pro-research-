"""Live-market BTC paper execution V3.

Real market data, simulated execution only. No exchange order submission.
Adds dynamic predictive support/resistance, ATR-based risk, failed-breakout /
liquidation-absorption gating, and persistent trade analytics.
"""

from __future__ import annotations
import json
import signal
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from strategy.predictive_levels_v1 import compute_levels, level_context

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "data/live_microstructure_state.json"
CANDLES = ROOT / "data/live_candles.json"
OUT = ROOT / "data/processed/live_execution_paper_v3.jsonl"
SUMMARY = ROOT / "data/processed/live_execution_paper_v3_summary.json"
LEVELS_OUT = ROOT / "data/processed/predictive_levels_live.json"
KILL = ROOT / "data/run/LIVE_KILL_SWITCH"

TICK = 0.50
CONTRACT_BTC = 0.001
FLOW_THRESHOLD = 0.10
MAX_STATE_AGE_S = 2.0
MAX_CANDLE_AGE_S = 180.0
MAX_ENTRY_AGE_S = 5.0
MAX_HOLD_S = 900.0
MAKER_FEE_BPS = 2.36
TAKER_FEE_BPS = 5.90
EXTRA_EXIT_TICKS = 1.0
RISK_FRACTION = 0.01
MAX_STOP_ATR = 1.25
MIN_RR = 1.50
MAX_TARGET_ATR = 4.0
ALLOW_LOW_VOLATILITY = False
RUNNING = True


def _stop(signum, frame):
    global RUNNING
    RUNNING = False


signal.signal(signal.SIGINT, _stop)
signal.signal(signal.SIGTERM, _stop)


def f(x, d=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


def read_json(path):
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def round_tick(p):
    return round(p / TICK) * TICK


def bps(a, b):
    return (b / a - 1.0) * 10000.0 if a > 0 else 0.0


LOG_MAX_BYTES = 2_000_000
_LOG_THROTTLE_S = 5.0
_last_log = {}


def append(row):
    OUT.parent.mkdir(parents=True, exist_ok=True)
    event = row.get("event", "")
    if event == "SIGNAL_BLOCK":
        key = (event, row.get("side"), row.get("reason"), row.get("level_reason"))
        now = time.time()
        if now - _last_log.get(key, 0.0) < _LOG_THROTTLE_S:
            return
        _last_log[key] = now
    payload = json.dumps(row, separators=(",", ":")) + "\n"
    try:
        if OUT.exists() and OUT.stat().st_size + len(payload.encode("utf-8")) > LOG_MAX_BYTES:
            with OUT.open("w", encoding="utf-8") as fh:
                fh.write(payload)
            return
    except OSError:
        pass
    with OUT.open("a", encoding="utf-8") as fh:
        fh.write(payload)


def current_levels(state):
    candles = read_json(CANDLES)
    if not isinstance(candles, list):
        return None
    px = f(state.get("order_book", {}).get("mid_price"))
    if px <= 0:
        return None
    levels = compute_levels(candles, px, state.get("order_book", {}))
    LEVELS_OUT.parent.mkdir(parents=True, exist_ok=True)
    LEVELS_OUT.write_text(json.dumps(levels.to_dict(), indent=2), encoding="utf-8")
    return levels


def absorption_signal(state):
    w5 = state.get("windows", {}).get("5", {})
    w30 = state.get("windows", {}).get("30", {})
    p5 = state.get("price", {}).get("5", {})
    ob = state.get("order_book", {})
    d5 = f(w5.get("delta_pct"))
    d30 = f(w30.get("delta_pct"))
    ret5 = f(p5.get("return_pct"))
    imb = f(ob.get("imbalance_5"))
    fresh = f(state.get("quality", {}).get("fresh_seconds"), 999)

    if fresh > MAX_STATE_AGE_S:
        return None, "STALE_DATA"

    # Heavy aggressive selling with little downside price response.
    if d5 <= -FLOW_THRESHOLD and d30 < 0 and ret5 > -0.06 and imb > -0.60:
        return "LONG", "SELL_ABSORPTION"
    # Heavy aggressive buying with little upside response.
    if d5 >= FLOW_THRESHOLD and d30 > 0 and ret5 < 0.06 and imb < 0.60:
        return "SHORT", "BUY_ABSORPTION"
    return None, "NO_ABSORPTION"


def executable_exit(state, side):
    ob = state.get("order_book", {})
    bid = f(ob.get("best_bid"))
    ask = f(ob.get("best_ask"))
    if bid <= 0 or ask <= 0:
        return 0.0
    return max(TICK, bid - EXTRA_EXIT_TICKS * TICK) if side == "LONG" else ask + EXTRA_EXIT_TICKS * TICK


def build_trade(side, entry, levels):
    atr = max(levels.atr, entry * 0.0008)
    if side == "LONG":
        structural = levels.nearest_support
        stop = min(entry - 0.25 * atr, (structural - 0.25 * atr) if structural else entry - atr)
        risk = entry - stop
        nearest = levels.nearest_resistance
        # Do not jump over a nearby resistance to manufacture an attractive RR.
        # If the first opposing structural level is too close, reject the trade.
        if nearest is None or nearest <= entry:
            return None
        if nearest < entry + risk * MIN_RR:
            return None
        target = nearest
    else:
        structural = levels.nearest_resistance
        stop = max(entry + 0.25 * atr, (structural + 0.25 * atr) if structural else entry + atr)
        risk = stop - entry
        nearest = levels.nearest_support
        # Do not jump over a nearby support to manufacture an attractive RR.
        if nearest is None or nearest >= entry:
            return None
        if nearest > entry - risk * MIN_RR:
            return None
        target = nearest

    max_risk = MAX_STOP_ATR * atr
    if risk <= 0 or risk > max_risk:
        return None
    rr = abs(target - entry) / risk
    if rr < MIN_RR or abs(target - entry) > MAX_TARGET_ATR * atr:
        return None
    return {
        "side": side,
        "entry": round_tick(entry),
        "stop": round_tick(stop),
        "target": round_tick(target),
        "risk_per_btc": round(risk, 4),
        "rr": round(rr, 3),
        "atr": round(atr, 4),
        "support": levels.nearest_support,
        "resistance": levels.nearest_resistance,
        "poc": levels.poc,
        "value_low": levels.value_low,
        "value_high": levels.value_high,
        "regime": levels.regime,
    }


def main(duration_s=86400, allow_low_volatility=False):
    global RUNNING, ALLOW_LOW_VOLATILITY
    ALLOW_LOW_VOLATILITY = bool(allow_low_volatility)
    started = time.time()
    position = None
    candidate = None
    trades = []
    stats = {
        "observations": 0,
        "signals": 0,
        "level_blocks": 0,
        "risk_blocks": 0,
        "entries": 0,
        "trades": 0,
        "wins": 0,
        "losses": 0,
        "stops": 0,
        "targets": 0,
        "timeouts": 0,
        "stale_blocks": 0,
        "kill_blocks": 0,
        "sum_net_usd": 0.0,
    }
    print("LIVE PAPER V3 STARTED | REAL ORDERS OFF | PREDICTIVE S/R + ATR RISK", flush=True)

    while RUNNING and time.time() - started < duration_s:
        state = read_json(STATE)
        stats["observations"] += 1
        if not state:
            time.sleep(0.25)
            continue

        fresh = f(state.get("quality", {}).get("fresh_seconds"), 999)
        if fresh > MAX_STATE_AGE_S:
            stats["stale_blocks"] += 1
            time.sleep(0.25)
            continue

        if KILL.exists():
            stats["kill_blocks"] += 1
            time.sleep(0.5)
            continue

        px = f(state.get("order_book", {}).get("mid_price"))
        bid = f(state.get("order_book", {}).get("best_bid"))
        ask = f(state.get("order_book", {}).get("best_ask"))
        if px <= 0 or bid <= 0 or ask <= 0:
            time.sleep(0.25)
            continue

        levels = current_levels(state)
        if levels is None:
            time.sleep(0.25)
            continue

        # Manage existing paper position.
        if position is not None:
            exit_px = executable_exit(state, position["side"])
            signed = bps(position["entry"], exit_px)
            if position["side"] == "SHORT":
                signed = -signed
            reason = None
            if position["side"] == "LONG" and exit_px <= position["stop"]:
                reason = "STOP"
            elif position["side"] == "LONG" and exit_px >= position["target"]:
                reason = "TARGET"
            elif position["side"] == "SHORT" and exit_px >= position["stop"]:
                reason = "STOP"
            elif position["side"] == "SHORT" and exit_px <= position["target"]:
                reason = "TARGET"
            elif time.time() - position["opened_at"] >= MAX_HOLD_S:
                reason = "TIME"

            if reason:
                notional = position["entry"] * CONTRACT_BTC
                entry_fee = notional * MAKER_FEE_BPS / 10000.0
                exit_fee = exit_px * CONTRACT_BTC * TAKER_FEE_BPS / 10000.0
                gross_usd = signed / 10000.0 * notional
                net_usd = gross_usd - entry_fee - exit_fee
                row = {
                    "ts": time.time(),
                    "event": "PAPER_EXIT",
                    "side": position["side"],
                    "entry": position["entry"],
                    "exit": exit_px,
                    "stop": position["stop"],
                    "target": position["target"],
                    "rr": position["rr"],
                    "gross_bps": round(signed, 4),
                    "net_bps": round(net_usd / notional * 10000.0, 4),
                    "net_usd": round(net_usd, 8),
                    "fees_usd": round(entry_fee + exit_fee, 8),
                    "hold_s": round(time.time() - position["opened_at"], 3),
                    "exit_reason": reason,
                    "levels": position["levels"],
                }
                append(row)
                trades.append(row)
                stats["trades"] += 1
                stats["sum_net_usd"] += net_usd
                if net_usd > 0:
                    stats["wins"] += 1
                else:
                    stats["losses"] += 1
                stats["stops" if reason == "STOP" else "targets" if reason == "TARGET" else "timeouts"] += 1
                position = None

        # Signal -> predictive level gate -> simulated entry.
        if position is None and candidate is None:
            side, reason = absorption_signal(state)
            # The existing live-paper sample was entirely LOW_VOLATILITY and deeply
            # negative. Keep this regime explicitly opt-in until it earns a fresh
            # out-of-sample positive edge.
            if side and not ALLOW_LOW_VOLATILITY and levels.regime == "LOW_VOLATILITY":
                stats["level_blocks"] += 1
                append({"ts": time.time(), "event": "REGIME_BLOCK", "side": side,
                        "reason": "LOW_VOLATILITY_UNVALIDATED", "levels": levels.to_dict()})
                side = None
                reason = "LOW_VOLATILITY_UNVALIDATED"
            if side:
                stats["signals"] += 1
                ctx = level_context(levels, side, max_distance_atr=1.25)
                if not ctx["eligible"]:
                    stats["level_blocks"] += 1
                    append({"ts": time.time(), "event": "SIGNAL_BLOCK",
                            "side": side, "reason": reason, "level_reason": ctx["reason"],
                            "levels": levels.to_dict()})
                else:
                    entry = bid if side == "LONG" else ask
                    plan = build_trade(side, entry, levels)
                    if plan is None:
                        stats["risk_blocks"] += 1
                        append({"ts": time.time(), "event": "RISK_BLOCK",
                                "side": side, "reason": "ATR_OR_RR_INVALID",
                                "levels": levels.to_dict()})
                    else:
                        candidate = {
                            "created_at": time.time(),
                            "side": side,
                            "reason": reason,
                            "plan": plan,
                            "levels": levels.to_dict(),
                        }
                        append({"ts": time.time(), "event": "PAPER_CANDIDATE", "candidate": candidate})

        if candidate is not None and position is None:
            if time.time() - candidate["created_at"] > MAX_ENTRY_AGE_S:
                append({"ts": time.time(), "event": "CANDIDATE_CANCEL", "reason": "ENTRY_TIMEOUT"})
                candidate = None
            else:
                side = candidate["side"]
                # Confirmation: price remains on the correct side of the reference
                # level and does not immediately invalidate the liquidity sweep.
                level = candidate["plan"]["support"] if side == "LONG" else candidate["plan"]["resistance"]
                near = abs(px - f(level)) <= max(candidate["plan"]["atr"] * 1.25, px * 0.0015) if level else False
                if near:
                    plan = candidate["plan"]
                    position = {
                        **plan,
                        "opened_at": time.time(),
                        "levels": candidate["levels"],
                        "signal_reason": candidate["reason"],
                    }
                    stats["entries"] += 1
                    append({"ts": time.time(), "event": "PAPER_ENTRY", "position": position})
                    candidate = None

        time.sleep(0.25)

    wins = [t["net_bps"] for t in trades if t["net_bps"] > 0]
    losses = [-t["net_bps"] for t in trades if t["net_bps"] < 0]
    summary = {
        **stats,
        "duration_s": round(time.time() - started, 3),
        "win_rate": len(wins) / len(trades) if trades else 0.0,
        "avg_net_bps": sum(t["net_bps"] for t in trades) / len(trades) if trades else 0.0,
        "profit_factor": sum(wins) / sum(losses) if losses else None,
        "expectancy_bps": sum(t["net_bps"] for t in trades) / len(trades) if trades else 0.0,
        "open_position": position,
        "status": "PAPER_ONLY",
        "real_orders": False,
        "promotion": "BLOCKED",
        "predictive_support_resistance": True,
        "risk_model": "1pct_reference; ATR-capped; min_RR_1.5",
        "fee_model": {"maker_bps": MAKER_FEE_BPS, "taker_bps": TAKER_FEE_BPS},
    }
    SUMMARY.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=int, default=86400)
    ap.add_argument("--allow-low-volatility", action="store_true",
                    help="Research-only override; still paper-only and never enables real orders.")
    args = ap.parse_args()
    main(args.seconds, args.allow_low_volatility)
