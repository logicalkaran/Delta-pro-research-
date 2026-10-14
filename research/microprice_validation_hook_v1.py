"""Research-only multi-level microprice feature + asynchronous 15s validator.

Input order_book fields expected:
  bids / asks: [[price, size], ...], best price first.
No orders are created. If per-level depth is unavailable, the hook abstains.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import time
from collections import deque
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATE = ROOT / "data" / "live_microstructure_state.json"
DEFAULT_OUT = ROOT / "data" / "processed" / "microprice_validation_v1.jsonl"
HORIZON_S = 15.0
MAX_STALE_S = 1.0
LEVELS = 5
DECAY_ALPHA = 0.4


def _levels(raw: Any, limit: int = LEVELS) -> list[tuple[float, float]]:
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw[:limit]:
        try:
            p, q = float(item[0]), float(item[1])
        except (TypeError, ValueError, IndexError):
            continue
        if math.isfinite(p) and math.isfinite(q) and p > 0 and q > 0:
            out.append((p, q))
    return out


def microprice_features(order_book: dict, alpha: float = DECAY_ALPHA) -> dict:
    """Decay-weighted N-level depth imbalance microprice.

    This is an explicitly defined research proxy with price-distance decay:
      tick = smallest observed positive adjacent level gap (fallback spread)
      B = sum(exp(-alpha * (best_bid - bid_price)/tick) * bid_size)
      A = sum(exp(-alpha * (ask_price - best_ask)/tick) * ask_size)
      I = (B-A)/(B+A)
      microprice = mid + (spread/2)*I

    It is not a claim that this proxy equals an optimal clearing price.
    """
    bids = _levels(order_book.get("bids") or order_book.get("bids_l5"))
    asks = _levels(order_book.get("asks") or order_book.get("asks_l5"))
    if not bids or not asks:
        return {"status": "MISSING_L2_LEVELS", "microprice": None,
                "mid": None, "spread": None, "imbalance_n": None,
                "shift_half_spread": None, "entry_threshold_pass": False}
    bid, ask = bids[0][0], asks[0][0]
    if bid >= ask:
        return {"status": "INVALID_OR_CROSSED_BOOK", "microprice": None,
                "mid": None, "spread": None, "imbalance_n": None,
                "shift_half_spread": None, "entry_threshold_pass": False}
    spread = ask - bid
    gaps=[]
    for side in (bids, asks):
        for i in range(1,len(side)):
            gap=abs(side[i-1][0]-side[i][0])
            if gap>0 and math.isfinite(gap): gaps.append(gap)
    tick_size=min(gaps) if gaps else spread
    if tick_size<=0: tick_size=spread
    bid_depth=sum(math.exp(-alpha*((bid-price)/tick_size))*q for price,q in bids)
    ask_depth=sum(math.exp(-alpha*((price-ask)/tick_size))*q for price,q in asks)
    denom = bid_depth + ask_depth
    if denom <= 0:
        return {"status": "EMPTY_DEPTH", "microprice": None,
                "mid": None, "spread": None, "imbalance_n": None,
                "shift_half_spread": None, "entry_threshold_pass": False}
    mid = (bid + ask) / 2.0
    spread = ask - bid
    imbalance = (bid_depth - ask_depth) / denom
    micro = mid + (spread / 2.0) * imbalance
    shift_half_spread = (micro - mid) / (spread / 2.0)
    return {
        "status": "OK",
        "levels_bid": len(bids), "levels_ask": len(asks), "inferred_tick_size": tick_size,
        "weighted_bid_depth": bid_depth, "weighted_ask_depth": ask_depth,
        "mid": mid, "spread": spread, "imbalance_n": imbalance,
        "microprice": micro, "microprice_shift": micro - mid,
        "shift_half_spread": shift_half_spread,
        "entry_threshold_pass": abs(shift_half_spread) >= 0.40,
        "direction": 1 if shift_half_spread >= 0.40 else
                     -1 if shift_half_spread <= -0.40 else 0,
        "alpha": alpha,
    }


def make_row(state: dict, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    ts = state.get("updated_at_epoch", state.get("timestamp", now))
    try:
        ts = float(ts)
    except (TypeError, ValueError):
        ts = now
    ob = state.get("order_book", {})
    features = microprice_features(ob)
    age = max(0.0, now - ts)
    return {
        "schema": "microprice_validation_v1",
        "ts_epoch": ts,
        "observed_at_epoch": now,
        "age_s": age,
        "fresh": age <= MAX_STALE_S,
        "symbol": state.get("symbol"),
        **features,
        "future_horizon_s": HORIZON_S,
        "future_mid_return_bps": None,
        "label_status": "PENDING" if features["status"] == "OK" and age <= MAX_STALE_S
                        else "UNAVAILABLE",
        "research_only": True,
        "real_orders": False,
        "production_changes": False,
    }


async def run_hook(state_path: Path = DEFAULT_STATE,
                   output_path: Path = DEFAULT_OUT,
                   interval_s: float = 1.0,
                   horizon_s: float = HORIZON_S,
                   max_runtime_s: float | None = None) -> None:
    """Poll state asynchronously, then attach 15s forward-mid labels.

    State must include order_book.bids and order_book.asks arrays of [price,size].
    Existing aggregate-only state intentionally yields MISSING_L2_LEVELS.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pending: deque[dict] = deque()
    started = time.monotonic()
    last_source_ts = None
    with output_path.open("a", encoding="utf-8") as out:
        while True:
            wall_now = time.time()
            if max_runtime_s is not None and time.monotonic() - started >= max_runtime_s:
                break
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
                row = make_row(state, wall_now)
                # Don't duplicate the same source snapshot.
                if row["ts_epoch"] != last_source_ts:
                    last_source_ts = row["ts_epoch"]
                    if row["status"] == "OK" and row["fresh"]:
                        pending.append(row)
                    else:
                        out.write(json.dumps(row, separators=(",", ":"), allow_nan=False) + "\n")
                        out.flush()

                ob = state.get("order_book", {})
                bids, asks = _levels(ob.get("bids") or ob.get("bids_l5")), _levels(ob.get("asks") or ob.get("asks_l5"))
                current_mid = ((bids[0][0] + asks[0][0]) / 2.0) if bids and asks and bids[0][0] < asks[0][0] else None
                now_ts = float(state.get("updated_at_epoch", state.get("timestamp", wall_now)))
                while pending and now_ts >= pending[0]["ts_epoch"] + horizon_s:
                    base = pending.popleft()
                    if current_mid is not None and base["mid"] > 0:
                        base["future_mid_return_bps"] = 10000.0 * math.log(current_mid / base["mid"])
                        base["label_status"] = "OK"
                    else:
                        base["label_status"] = "MISSING_FUTURE_BOOK"
                    out.write(json.dumps(base, separators=(",", ":"), allow_nan=False) + "\n")
                    out.flush()
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                pass
            await asyncio.sleep(max(0.05, interval_s))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default=str(DEFAULT_STATE))
    ap.add_argument("--output", default=str(DEFAULT_OUT))
    ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--horizon", type=float, default=HORIZON_S)
    ap.add_argument("--runtime", type=float, default=None, help="optional bounded runtime seconds")
    args = ap.parse_args()
    asyncio.run(run_hook(Path(args.state), Path(args.output), args.interval,
                         args.horizon, args.runtime))


if __name__ == "__main__":
    main()
