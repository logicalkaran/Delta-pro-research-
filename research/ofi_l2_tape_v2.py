"""Capture bounded L5 state snapshots for OFI research; read-only, no orders.

Important: updated_at_epoch is a local state-refresh timestamp, not a confirmed
exchange-native book-event timestamp. Output OFI is sampled-state delta only.
"""
from __future__ import annotations
import json, time, uuid, argparse, math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "data/live_microstructure_state.json"
OUT = ROOT / "data/processed/ofi_l2_snapshots_v2.jsonl"
MAX_BYTES = 20_000_000
POLL_S = 0.25
MAX_SOURCE_AGE_S = 2.0


def levels(v):
    out = []
    for x in v or []:
        try:
            p, q = float(x[0]), float(x[1])
            if math.isfinite(p) and math.isfinite(q) and p > 0 and q >= 0:
                out.append([p, q])
        except (ValueError, TypeError, IndexError):
            continue
    return out[:5]


def snapshot(d, session_id):
    ob = d.get("order_book") or {}
    quality = d.get("quality") or {}
    raw_ts = d.get("updated_at_epoch")
    try:
        ts = float(raw_ts)
        ts_valid = math.isfinite(ts) and ts > 0
    except (ValueError, TypeError):
        ts, ts_valid = None, False
    try:
        age = float(quality.get("fresh_seconds"))
        age_valid = math.isfinite(age) and age >= 0
    except (ValueError, TypeError):
        age, age_valid = None, False
    return {
        "session_id": session_id,
        "ts": ts if ts_valid else None,
        "timestamp_kind": "local_state_refresh_not_exchange_book_event",
        "source_event_timestamp_present": False,
        "timestamp_valid": ts_valid,
        "symbol": d.get("symbol", "BTCUSD"),
        "mid": float(ob.get("mid_price", 0) or 0),
        "bid": float(ob.get("best_bid", 0) or 0),
        "ask": float(ob.get("best_ask", 0) or 0),
        "spread": float(ob.get("spread", 0) or 0),
        "bids_l5": levels(ob.get("bids_l5")),
        "asks_l5": levels(ob.get("asks_l5")),
        "trade_samples": int(quality.get("trade_samples", 0) or 0),
        "reported_book_samples": int(quality.get("book_samples", 0) or 0),
        "source_fresh_seconds": age if age_valid else None,
        "source_age_valid": age_valid,
    }


def side_delta(prev, current, side):
    total = 0.0
    for i in range(5):
        pp, pv = prev[i] if i < len(prev) else [0.0, 0.0]
        cp, cv = current[i] if i < len(current) else [0.0, 0.0]
        if pp <= 0 or cp <= 0:
            continue
        if side == "bid":
            delta = cv if cp > pp else (cv - pv if cp == pp else -pv)
        else:
            delta = cv if cp < pp else (cv - pv if cp == pp else -pv)
        total += delta
    return total


def ofi(prev, cur):
    db = side_delta(prev["bids_l5"], cur["bids_l5"], "bid")
    da = side_delta(prev["asks_l5"], cur["asks_l5"], "ask")
    return {"ofi_bid_l5": db, "ofi_ask_l5": da, "ofi_l5": db - da}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("seconds", nargs="?", type=int, default=21600)
    args = parser.parse_args()
    deadline = time.monotonic() + max(1, args.seconds)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    sid = "ofi_l2_" + time.strftime("%Y%m%d_%H%M%S", time.gmtime()) + "_" + uuid.uuid4().hex[:6]
    last_ts = None
    prev = None
    last_poll = 0
    while time.monotonic() < deadline:
        now = time.time()
        if now - last_poll >= POLL_S and STATE.exists():
            last_poll = now
            try:
                d = json.loads(STATE.read_text())
                cur = snapshot(d, sid)
                valid_book = (cur["mid"] > 0 and cur["bid"] > 0 and cur["ask"] >= cur["bid"]
                              and bool(cur["bids_l5"]) and bool(cur["asks_l5"]))
                fresh = (cur["source_age_valid"] and cur["source_fresh_seconds"] <= MAX_SOURCE_AGE_S)
                if cur["timestamp_valid"] and cur["ts"] != last_ts and valid_book:
                    cur["snapshot_index"] = 0 if prev is None else prev["snapshot_index"] + 1
                    if not fresh:
                        cur.update({"ofi_bid_l5": None, "ofi_ask_l5": None, "ofi_l5": None,
                                    "ofi_status": "REJECTED_STALE_SOURCE"})
                    elif prev is None or cur["ts"] <= prev["ts"]:
                        cur.update({"ofi_bid_l5": None, "ofi_ask_l5": None, "ofi_l5": None,
                                    "ofi_status": "NO_VALID_PREVIOUS_TIMESTAMP"})
                    else:
                        cur.update(ofi(prev, cur))
                        cur["ofi_status"] = "SAMPLED_STATE_DELTA_NOT_EXCHANGE_EVENT_OFI"
                    with OUT.open("a") as f:
                        f.write(json.dumps(cur, separators=(",", ":")) + "\n")
                    # Only a fresh, valid timestamp/book can become the next reference.
                    if fresh:
                        prev = cur
                        last_ts = cur["ts"]
                    if OUT.stat().st_size > MAX_BYTES:
                        lines = OUT.read_text().splitlines()
                        OUT.write_text("\n".join(lines[-max(1000, len(lines) // 2):]) + "\n")
            except (ValueError, TypeError, KeyError, OSError):
                pass
        time.sleep(0.05)


if __name__ == "__main__":
    main()
