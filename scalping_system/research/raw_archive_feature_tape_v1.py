"""Streaming event-level feature tape built from immutable Delta raw archives.

This is an offline/replay companion to live_microstructure_feature_tape_v1.py. It does
not read the rolling mirror when a gzip session is selected, and does not place orders.
Memory is bounded to the current record plus a one-second trade-flow deque.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

try:
    from research.raw_archive_reader_v1 import DEFAULT_ARCHIVE_DIR, DEFAULT_LEGACY_PATH, iter_raw_records
    from research.microprice_validation_hook_v1 import microprice_features
except ModuleNotFoundError:
    from raw_archive_reader_v1 import DEFAULT_ARCHIVE_DIR, DEFAULT_LEGACY_PATH, iter_raw_records
    from microprice_validation_hook_v1 import microprice_features


def _f(x: Any) -> float | None:
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def _event_time(record: dict[str, Any], message: dict[str, Any]) -> float | None:
    ns = _f(record.get("receive_epoch_ns"))
    if ns is not None and ns > 0:
        return ns / 1_000_000_000
    received = record.get("received_at")
    if isinstance(received, str):
        try:
            return datetime.fromisoformat(received.replace("Z", "+00:00")).timestamp()
        except ValueError:
            pass
    # Delta event ts/t are microseconds. Used only when no receive timestamp exists.
    for key in ("ts", "t"):
        value = _f(message.get(key))
        if value is not None and value > 100_000_000_000_000:
            return value / 1_000_000
    return None


def stream_feature_rows(records: Iterable[dict[str, Any]], session_id: str = "UNSCOPED"):
    flow: deque[tuple[float, float]] = deque()
    pending_replenishment: deque[dict[str, Any]] = deque()
    latest_delta_book: dict[str, Any] | None = None
    last_replenishment: dict[str, Any] = {"rate": None, "status": "NO_MATCHED_SELL_SWEEP"}
    replenishment_count = 0
    seq = 0
    for record in records:
        message = record.get("message", record)
        if not isinstance(message, dict):
            continue
        ts = _event_time(record, message)
        if ts is None:
            continue
        typ = message.get("type")
        if typ == "trades":
            price, size, side = _f(message.get("p")), _f(message.get("s")), message.get("r")
            if price is not None and size is not None and size > 0 and side in ("m", "t"):
                flow.append((ts, -size if side == "m" else size))
                # Provisional project convention: r='m' is an aggressive sell. This must
                # be verified against venue semantics before interpreting the feature.
                if side == "m" and latest_delta_book is not None and latest_delta_book.get("is_l2") and price == latest_delta_book["best_bid"]:
                    match = next((p for p in reversed(pending_replenishment)
                                  if p["price"] == price and ts <= p["window_end"]), None)
                    if match is not None:
                        match["sell_volume"] += size
                    else:
                        pending_replenishment.append({"start_ts": ts, "window_end": ts + 0.2,
                            "price": price, "pre_size": latest_delta_book["bid_size_at_price"],
                            "sell_volume": size})
            while flow and ts >= flow[0][0] and ts - flow[0][0] > 1.0:
                flow.popleft()
            while pending_replenishment and ts > pending_replenishment[0]["window_end"] + 0.5:
                pending_replenishment.popleft()
            continue
        if typ not in ("ob_l2", "ob_l1"):
            continue
        if typ == "ob_l2":
            bids = message.get("b") if isinstance(message.get("b"), list) else []
            asks = message.get("a") if isinstance(message.get("a"), list) else []
        else:
            bids = [[message.get("bp"), message.get("bs")]]
            asks = [[message.get("ap"), message.get("as")]]
        if not bids or not asks:
            continue
        bid, ask = _f(bids[0][0]), _f(asks[0][0])
        bq, aq = _f(bids[0][1]), _f(asks[0][1])
        if bid is None or ask is None or bq is None or aq is None or bid <= 0 or ask <= bid or bq < 0 or aq < 0:
            continue
        mid, spread = (bid + ask) / 2.0, ask - bid
        bid_size_at_price = None
        if typ == "ob_l2":
            bid_size_at_price = next((_f(level[1]) for level in bids
                                      if isinstance(level, (list, tuple)) and len(level) >= 2
                                      and _f(level[0]) == bid), None)
        else:
            bid_size_at_price = bq
        # Resolve only after the full 200ms response window. Use the first subsequent
        # snapshot in [window_end, window_end+500ms]; never interpolate missing depth.
        while typ == "ob_l2" and pending_replenishment and ts >= pending_replenishment[0]["window_end"]:
            pending = pending_replenishment.popleft()
            if ts - pending["window_end"] > 0.5:
                continue
            post_size = next((_f(level[1]) for level in bids
                              if isinstance(level, (list, tuple)) and len(level) >= 2
                              and _f(level[0]) == pending["price"]), 0.0)
            pre_size, sold = pending["pre_size"], pending["sell_volume"]
            if pre_size is not None and sold > 0:
                # Same-venue contract units only: (post - pre + aggressive sell volume) / sell volume.
                rate = (post_size - pre_size + sold) / sold
                last_replenishment = {"rate": rate, "status": "OK", "price": pending["price"],
                    "pre_bid_size": pre_size, "post_bid_size": post_size, "sell_volume": sold,
                    "observed_at_ts": ts, "window_ms": (ts - pending["start_ts"]) * 1000}
                replenishment_count += 1
            else:
                last_replenishment = {"rate": None, "status": "MISSING_PRE_DEPTH_OR_SELL_VOLUME"}
        if typ == "ob_l2":
            latest_delta_book = {"best_bid": bid, "best_ask": ask, "bid_size_at_price": bid_size_at_price, "is_l2": True}
        micro = microprice_features({"bids": bids, "asks": asks}) if typ == "ob_l2" else {}
        while flow and ts >= flow[0][0] and ts - flow[0][0] > 1.0:
            flow.popleft()
        seq += 1
        replenishment_ts = last_replenishment.get("observed_at_ts")
        replenishment_rate = last_replenishment.get("rate") if replenishment_ts is not None and 0 <= ts - replenishment_ts <= 1.0 else None
        if micro.get("direction") == 1:
            replenishment_gate = "PASS" if replenishment_rate is not None and replenishment_rate >= 0 else "VETO" if replenishment_rate is not None and replenishment_rate < 0 else "UNKNOWN_ABSTAIN"
        else:
            replenishment_gate = "NOT_APPLICABLE"
        yield {
            "schema": "raw_archive_feature_tape_v1", "session_id": session_id,
            "arrival_sequence": seq, "receive_ts_epoch": ts, "ts": ts,
            "exchange_ts": message.get("ts", message.get("t")), "source_type": typ,
            "symbol": message.get("sy"), "bid": bid, "ask": ask, "mid": mid,
            "spread": spread, "spread_bps": spread / mid * 10000.0,
            "bid_size_l1": bq, "ask_size_l1": aq,
            "l1_imbalance": (bq - aq) / (bq + aq) if bq + aq > 0 else None,
            "signed_flow_1s": sum(v for _, v in flow),
            "microprice_method": "price_distance_decay_v1" if typ == "ob_l2" and micro.get("status") == "OK" else None,
            "microprice_imbalance_n": micro.get("imbalance_n"),
            "microprice_direction": micro.get("direction", 0),
            "microprice_threshold_pass": micro.get("entry_threshold_pass", False),
            "microprice": micro.get("microprice"), "microprice_status": micro.get("status", "L1_ONLY"),
            "microprice_shift_half_spread": micro.get("shift_half_spread"),
            "delta_bid_replenishment_rate_200ms": replenishment_rate,
            "delta_bid_replenishment_status": "OK" if replenishment_rate is not None else "STALE_OR_MISSING",
            "delta_bid_replenishment_window_ms": last_replenishment.get("window_ms") if replenishment_rate is not None else None,
            "delta_bid_replenishment_observations": replenishment_count,
            "delta_bid_replenishment_details": dict(last_replenishment),
            "microprice_bullish_replenishment_gate": replenishment_gate,
            "signed_trade_flow_1s": sum(v for _, v in flow), "trade_events_1s": len(flow),
            "research_only": True, "real_orders": False,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--archive-dir", type=Path, default=DEFAULT_ARCHIVE_DIR)
    parser.add_argument("--legacy-path", type=Path, default=DEFAULT_LEGACY_PATH)
    parser.add_argument("--output", type=Path, required=True, help="feature JSONL output path")
    args = parser.parse_args()
    try:
        records = iter_raw_records(args.session_id, args.archive_dir, args.legacy_path)
        archive_paths = list(args.archive_dir.glob("session_*_part_*.jsonl.gz")) if args.archive_dir.exists() else []
        if args.session_id:
            tape_session = args.session_id
        elif archive_paths:
            sessions = sorted({p.name[len("session_"):].rsplit("_part_", 1)[0] for p in archive_paths})
            tape_session = sessions[0] if len(sessions) == 1 else "MULTI_SESSION_REJECTED"
        else:
            tape_session = "LEGACY_TAIL_INCOMPLETE"
        args.output.parent.mkdir(parents=True, exist_ok=True)
        count = 0
        with args.output.open("x", encoding="utf-8") as out:
            for row in stream_feature_rows(records, tape_session):
                out.write(json.dumps(row, separators=(",", ":"), allow_nan=False) + "\n")
                count += 1
        print(json.dumps({"status": "OK", "rows": count, "output": str(args.output),
                          "session_id": tape_session, "research_only": True, "real_orders": False}, indent=2))
        return 0
    except (OSError, ValueError) as exc:
        print(f"FAILED_CLOSED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
