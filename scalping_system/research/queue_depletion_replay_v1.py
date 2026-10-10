"""Pessimistic passive bid-fill replay over archived Delta raw events.

Research-only. No exchange APIs, orders, or production-strategy imports. One theoretical
bid is armed per eligible L2 snapshot while no order is active. Queue depletion requires
aggressive sell volume >= displayed queue-ahead + our configured order size. If exact-tier
trade-side/size evidence is ambiguous, a best-ask-through is the only fallback fill rule.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable

try:
    from research.raw_archive_reader_v1 import DEFAULT_ARCHIVE_DIR, DEFAULT_LEGACY_PATH, iter_raw_records
except ModuleNotFoundError:
    from raw_archive_reader_v1 import DEFAULT_ARCHIVE_DIR, DEFAULT_LEGACY_PATH, iter_raw_records

HORIZONS = (1, 5, 15, 30, 60)
D0 = Decimal("0")


def dec(value: Any) -> Decimal | None:
    try:
        out = Decimal(str(value))
        return out if out.is_finite() else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def receive_seconds(record: dict[str, Any], message: dict[str, Any]) -> float | None:
    ns = dec(record.get("receive_epoch_ns"))
    if ns is not None and ns > 0:
        return float(ns / Decimal(1_000_000_000))
    stamp = record.get("received_at")
    if isinstance(stamp, str):
        try:
            return datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()
        except ValueError:
            pass
    # Older captures may only have exchange timestamps (Delta ts/t are microseconds).
    for key in ("ts", "t"):
        value = dec(message.get(key))
        if value is not None and value > Decimal("100000000000000"):
            return float(value / Decimal(1_000_000))
        if value is not None and value > Decimal("1000000000"):
            return float(value)
    return None


def _levels(value: Any) -> list[tuple[Decimal, Decimal]]:
    if not isinstance(value, list):
        return []
    out = []
    for item in value:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        price, size = dec(item[0]), dec(item[1])
        if price is not None and size is not None and price > 0 and size >= 0:
            out.append((price, size))
    return out


def _mid(bid: Decimal | None, ask: Decimal | None) -> Decimal | None:
    if bid is None or ask is None or bid <= 0 or ask <= 0 or ask < bid:
        return None
    return (bid + ask) / Decimal(2)


def _microprice(bid: Decimal, ask: Decimal, bid_size: Decimal, ask_size: Decimal) -> Decimal | None:
    denom = bid_size + ask_size
    if denom <= 0 or ask < bid:
        return None
    return (ask * bid_size + bid * ask_size) / denom


def replay(records: Iterable[dict[str, Any]], order_size: Decimal = Decimal("1"), timeout_s: float = 60.0) -> dict[str, Any]:
    if order_size <= 0:
        raise ValueError("order_size must be positive")
    if timeout_s <= 0:
        raise ValueError("timeout_s must be positive")

    best_bid = best_ask = bid_size = ask_size = None
    current_mid = None
    active: dict[str, Any] | None = None
    pending_marks: list[dict[str, Any]] = []
    fills: list[dict[str, Any]] = []
    missed: list[dict[str, Any]] = []
    terminal: list[dict[str, Any]] = []
    counts = {"records": 0, "l1_snapshots": 0, "l2_snapshots": 0, "trades": 0,
              "orders_placed": 0, "queue_depletion_fills": 0, "price_through_fills": 0,
              "adverse_momentum_misses": 0, "microprice_reversion_cancels": 0,
              "queue_front_running_cancels": 0, "timeouts": 0, "ambiguous_exact_tier_trades": 0}
    last_event_time = None
    order_seq = 0

    def finalize_fill(order: dict[str, Any], ts: float, reason: str) -> None:
        row = {"order_id": order["order_id"], "placed_at": order["placed_at"], "fill_at": ts,
               "limit_price": float(order["limit_price"]), "queue_ahead_initial": float(order["queue_ahead"]),
               "our_order_size": float(order_size), "sell_volume_at_limit": float(order["sell_volume"]),
               "fill_reason": reason, "markouts_bps": {str(h): None for h in HORIZONS}}
        fills.append(row)
        pending_marks.append({"row": row, "fill_at": ts, "done": set()})
        if reason == "QUEUE_DEPLETION": counts["queue_depletion_fills"] += 1
        else: counts["price_through_fills"] += 1

    for record in records:
        if not isinstance(record, dict):
            continue
        counts["records"] += 1
        message = record.get("message", record)
        if not isinstance(message, dict):
            continue
        event_ts = receive_seconds(record, message)
        if event_ts is None:
            continue
        # Arrival order is authoritative. Do not sort by venue timestamps and invent causality.
        last_event_time = event_ts
        typ = message.get("type")
        is_book = False
        cancelled_this_event = False

        if typ == "ob_l1":
            counts["l1_snapshots"] += 1
            b, a = dec(message.get("bp")), dec(message.get("ap"))
            bs, ass = dec(message.get("bs")), dec(message.get("as"))
            if b is not None and a is not None and b > 0 and a >= b:
                best_bid, best_ask = b, a
                bid_size = max(D0, bs or D0)
                ask_size = max(D0, ass or D0)
                is_book = True
        elif typ == "ob_l2":
            counts["l2_snapshots"] += 1
            bids, asks = _levels(message.get("b")), _levels(message.get("a"))
            if bids and asks:
                b, bs = max(bids, key=lambda x: x[0])
                a, ass = min(asks, key=lambda x: x[0])
                if b > 0 and a >= b:
                    best_bid, bid_size, best_ask, ask_size = b, bs, a, ass
                    is_book = True

        current_mid = _mid(best_bid, best_ask)
        if is_book and current_mid is not None:
            # Markouts use the first received book snapshot at/after each target horizon.
            for pending in pending_marks:
                for horizon in HORIZONS:
                    if horizon in pending["done"] or event_ts < pending["fill_at"] + horizon:
                        continue
                    markout = (current_mid - Decimal(str(pending["row"]["limit_price"]))) / Decimal(str(pending["row"]["limit_price"])) * Decimal(10000)
                    pending["row"]["markouts_bps"][str(horizon)] = float(markout)
                    pending["done"].add(horizon)

        if typ == "trades":
            counts["trades"] += 1
            if active is not None:
                price, size = dec(message.get("p")), dec(message.get("s"))
                # Project's existing Delta convention: r='m' is aggressive sell, r='t' buy.
                # Any other side token is treated as ambiguous, never guessed as a sell.
                side = message.get("r")
                if price == active["limit_price"]:
                    if side in ("m", "t") and size is not None and size > 0:
                        active["volume_observable"] = True
                        if side == "m":
                            active["sell_volume"] += size
                            active["last_exact_tier_sell_at"] = event_ts
                    else:
                        active["volume_observable"] = False
                        counts["ambiguous_exact_tier_trades"] += 1

        if active is not None and is_book and current_mid is not None and best_bid is not None and best_ask is not None:
            micro_now = _microprice(best_bid, best_ask, bid_size or D0, ask_size or D0)
            if micro_now is not None and active.get("microprice_was_above_mid", False) and micro_now < current_mid:
                missed.append({"order_id": active["order_id"], "status": "MISSED_FILL",
                    "reason": "MICROPRICE_REVERTED_BELOW_MID", "at": event_ts,
                    "limit_price": float(active["limit_price"]), "queue_ahead_initial": float(active["queue_ahead"]),
                    "sell_volume_at_limit": float(active["sell_volume"])})
                counts["microprice_reversion_cancels"] += 1
                active = None
                cancelled_this_event = True
            elif active is not None and typ == "ob_l2":
                bids_now = _levels(message.get("b"))
                level_size = next((size for price, size in bids_now if price == active["limit_price"]), D0)
                prior_size = active.get("last_level_size", active["queue_ahead"])
                if level_size > prior_size:
                    missed.append({"order_id": active["order_id"], "status": "MISSED_FILL",
                        "reason": "DISPLAYED_QUEUE_SIZE_INCREASE_PROXY", "at": event_ts,
                        "limit_price": float(active["limit_price"]), "queue_ahead_initial": float(active["queue_ahead"]),
                        "previous_displayed_size": float(prior_size), "new_displayed_size": float(level_size),
                        "sell_volume_at_limit": float(active["sell_volume"])})
                    counts["queue_front_running_cancels"] += 1
                    active = None
                    cancelled_this_event = True
                else:
                    active["last_level_size"] = level_size
            if active is not None and micro_now is not None:
                active["microprice_was_above_mid"] = micro_now >= current_mid

        if active is not None:
            # Strict queue depletion: volume must clear all displayed volume ahead AND our size.
            hurdle = active["queue_ahead"] + order_size
            if active["volume_observable"] and active["sell_volume"] >= hurdle:
                finalize_fill(active, event_ts, "QUEUE_DEPLETION")
                active = None
            elif best_ask is not None and best_ask <= active["limit_price"] and not active["volume_observable"]:
                finalize_fill(active, event_ts, "PRICE_THROUGH_AMBIGUOUS_TRADE_FLOW")
                active = None
            elif event_ts - active["placed_at"] >= timeout_s:
                terminal.append({"order_id": active["order_id"], "status": "NOT_FILLED_TIMEOUT", "at": event_ts})
                counts["timeouts"] += 1
                active = None
            elif current_mid is not None and best_bid is not None and best_ask is not None:
                half_spread = (best_ask - best_bid) / Decimal(2)
                micro = _microprice(best_bid, best_ask, bid_size or D0, ask_size or D0)
                adverse_threshold = current_mid - Decimal("0.4") * half_spread
                # Cancel only while displayed queue-ahead has not been depleted.
                if micro is not None and micro < adverse_threshold and active["sell_volume"] < active["queue_ahead"]:
                    missed.append({"order_id": active["order_id"], "status": "MISSED_FILL", "reason": "ADVERSE_MICROPRICE_BEFORE_QUEUE_DEPLETION", "at": event_ts,
                                   "limit_price": float(active["limit_price"]), "queue_ahead_initial": float(active["queue_ahead"]),
                                   "sell_volume_at_limit": float(active["sell_volume"])})
                    counts["adverse_momentum_misses"] += 1
                    active = None

        # Place only on an L2 snapshot; never infer queue-ahead from the L1 compatibility feed.
        # A new order is armed after the current order terminates, on the next valid L2 event.
        if typ == "ob_l2" and is_book and active is None and not cancelled_this_event and best_bid is not None and best_ask is not None and best_ask > best_bid:
            bids = _levels(message.get("b"))
            exact = next((size for price, size in bids if price == best_bid), None)
            if exact is not None:
                order_seq += 1
                micro_at_entry = _microprice(best_bid, best_ask, bid_size or D0, ask_size or D0)
                active = {"order_id": order_seq, "placed_at": event_ts, "limit_price": best_bid,
                          "queue_ahead": exact, "last_level_size": exact, "sell_volume": D0,
                          "volume_observable": False,
                          "microprice_was_above_mid": micro_at_entry is not None and current_mid is not None and micro_at_entry >= current_mid}
                counts["orders_placed"] += 1

    if active is not None:
        terminal.append({"order_id": active["order_id"], "status": "NOT_FILLED_END_OF_ARCHIVE", "at": last_event_time})
    for pending in pending_marks:
        pending["row"]["markout_complete"] = len(pending["done"]) == len(HORIZONS)

    markout_summary = {}
    for horizon in HORIZONS:
        values = [row["markouts_bps"][str(horizon)] for row in fills if row["markouts_bps"][str(horizon)] is not None]
        markout_summary[str(horizon)] = {"n": len(values), "mean_bps": statistics.fmean(values) if values else None,
                                         "median_bps": statistics.median(values) if values else None,
                                         "negative_mean": bool(values) and statistics.fmean(values) < 0}
    return {"schema": "queue_depletion_replay_v1", "research_only": True, "real_orders": False,
            "fill_model": {"order_size": float(order_size), "timeout_seconds": timeout_s,
                           "queue_hurdle": "aggressive_sell_volume_at_exact_bid >= displayed_queue_ahead + order_size",
                           "price_through_fallback": "best_ask <= limit_price only when exact-tier trade evidence is ambiguous",
                           "adverse_cancel": "microprice < mid - 0.4 * half_spread while sell_volume < queue_ahead",
                           "microprice_reversion_cancel": "cancel if microprice was at/above mid and crosses below mid",
                           "queue_front_running_cancel": "cancel if displayed size at the limit price increases; conservative proxy only, not observable true queue priority",
                           "markout_sampling": "first received L1/L2 book snapshot at or after each horizon; no interpolation"},
            "counts": counts, "fill_count": len(fills), "missed_fill_count": len(missed),
            "nonfill_terminal_count": len(terminal), "markout_summary_bps": markout_summary,
            "fills": fills, "missed_fills": missed, "nonfills": terminal,
            "limitations": ["This is a conservative proxy, not exchange-confirmed queue position.",
                            "Delta r='m' sell-side interpretation follows the existing local parser and must be validated against venue documentation.",
                            "A bounded legacy JSONL mirror is incomplete history; only immutable gzip session partitions qualify as full-session evidence."]}


def main() -> int:
    parser = argparse.ArgumentParser(description="Dry-run pessimistic passive-fill replay; no trading")
    parser.add_argument("--session-id", default=None, help="explicit gzip session ID; replayed in partition/arrival order")
    parser.add_argument("--archive-dir", type=Path, default=DEFAULT_ARCHIVE_DIR)
    parser.add_argument("--legacy-path", type=Path, default=DEFAULT_LEGACY_PATH)
    parser.add_argument("--order-size", default="1", help="theoretical order size in exchange quantity units")
    parser.add_argument("--timeout-seconds", type=float, default=60.0)
    parser.add_argument("--output", type=Path, default=None, help="optional JSON report path")
    args = parser.parse_args()
    try:
        report = replay(iter_raw_records(args.session_id, args.archive_dir, args.legacy_path), dec(args.order_size) or D0, args.timeout_seconds)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    rendered = json.dumps(report, indent=2, allow_nan=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(json.dumps({"schema": report["schema"], "counts": report["counts"], "fill_count": report["fill_count"],
                      "missed_fill_count": report["missed_fill_count"], "nonfill_terminal_count": report["nonfill_terminal_count"],
                      "markout_summary_bps": report["markout_summary_bps"], "output": str(args.output) if args.output else None}, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
