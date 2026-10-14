"""Research-only normalization, direction-aware deduplication and purged walk-forward splits.

No filesystem mutation, trading, network access, or model promotion occurs here.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import math
from typing import Any, Iterable

TIMESTAMP_KEYS = (
    "ts", "timestamp", "timestamp_ns", "timestamp_us", "timestamp_ms",
    "ts_ns", "ts_us", "ts_ms", "time", "time_ns", "time_us", "time_ms",
    "exchange_timestamp", "received_at", "local_timestamp", "created_at",
    "event_time", "E", "T",
)


def normalize_timestamp(value: Any, key: str = "") -> float:
    """Normalize a supported epoch or ISO-8601 timestamp to UTC epoch seconds."""
    if value is None or isinstance(value, bool):
        raise ValueError("missing_or_invalid_timestamp")
    if isinstance(value, str):
        text = value.strip()
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            # Naive ISO timestamps are interpreted as UTC, never device-local time.
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            value = parsed.timestamp()
        except ValueError:
            try:
                value = float(text)
            except ValueError as exc:
                raise ValueError("unparseable_timestamp") from exc
    if not isinstance(value, (int, float)):
        raise ValueError("unsupported_timestamp_type")
    value = float(value)
    lower_key = key.lower()
    if lower_key.endswith("_ns") or lower_key == "timestamp_ns":
        value /= 1e9
    elif lower_key.endswith("_us") or lower_key == "timestamp_us":
        value /= 1e6
    elif lower_key.endswith("_ms") or lower_key == "timestamp_ms":
        value /= 1e3
    elif value > 1e17:
        value /= 1e9
    elif value > 1e14:
        value /= 1e6
    elif value > 1e11:
        value /= 1e3
    if not math.isfinite(value):
        raise ValueError("timestamp_non_finite")
    if value <= 0:
        raise ValueError("timestamp_out_of_range")
    return value


def timestamp_from_record(record: dict[str, Any]) -> tuple[float, str]:
    """Read top-level or known nested exchange timestamp fields."""
    for key in TIMESTAMP_KEYS:
        if record.get(key) is not None:
            return normalize_timestamp(record[key], key), key
    message = record.get("message")
    if isinstance(message, dict):
        for key in ("ts", "timestamp", "time", "lts", "E", "T"):
            if message.get(key) is not None:
                return normalize_timestamp(message[key], key), f"message.{key}"
    raise ValueError("missing_timestamp")


def _first(record: dict[str, Any], keys: tuple[str, ...], default=None):
    for key in keys:
        if record.get(key) is not None:
            return record[key]
    return default


def classify_schema(record: dict[str, Any]) -> str:
    """Heuristic schema class; UNKNOWN is intentionally fail-closed."""
    if isinstance(record.get("message"), dict):
        msg = record["message"]
        kind = str(msg.get("type", record.get("type", ""))).lower()
        if "trade" in kind or any(k in msg for k in ("price", "size", "trade_id")):
            return "market_trades"
        if any(k in msg for k in ("ap", "bp", "asks", "bids", "depth")):
            return "orderbook_depth"
    keys = set(record)
    if any(k in keys for k in ("order_id", "client_order_id", "execution_id", "fill_id")):
        return "execution_journal"
    if "labels" in keys or "label" in keys or "target" in keys:
        return "labeled_dataset"
    if any(k in keys for k in ("imb5", "imb10", "delta5", "delta30", "features", "regime")):
        return "derived_features"
    if any(k in keys for k in ("price", "size", "trade_id")):
        return "market_trades"
    if any(k in keys for k in ("bids", "asks", "depth", "book")):
        return "orderbook_depth"
    return "unknown"


def normalize_and_sort(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Return sorted copies, preserving source index and reporting timestamp failures/inversions."""
    normalized = []
    missing = 0
    original_times = []
    for index, source in enumerate(records):
        if not isinstance(source, dict):
            missing += 1
            continue
        row = dict(source)
        try:
            ts, source_key = timestamp_from_record(row)
        except ValueError:
            missing += 1
            continue
        original_times.append((index, ts))
        row["ts_utc_s"] = ts
        row["_source_index"] = index
        row["_timestamp_source_key"] = source_key
        row["_schema_type"] = classify_schema(source)
        normalized.append(row)
    inversions = sum(
        current_ts < previous_ts
        for (_, previous_ts), (_, current_ts) in zip(original_times, original_times[1:])
    )
    normalized.sort(key=lambda row: (
        row["ts_utc_s"],
        str(_first(row, ("event_type", "type"), "")),
        str(_first(row, ("sequence_id", "sequence", "seq"), "")),
        row["_source_index"],
    ))
    return {
        "records": normalized,
        "input_records": len(list(records)) if not isinstance(records, list) else len(records),
        "timestamp_missing_or_invalid": missing,
        "original_order_inversions": inversions,
        "sort_is_stable": True,
    }


def deduplicate_records(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Deduplicate ticks and labels with separate keys; never collapse LONG vs SHORT."""
    kept = []
    seen = set()
    dropped = Counter()
    for source in records:
        row = dict(source)
        try:
            ts = float(row.get("ts_utc_s", timestamp_from_record(row)[0]))
        except (ValueError, TypeError):
            dropped["missing_timestamp"] += 1
            continue
        row["ts_utc_s"] = ts
        schema = row.get("_schema_type") or classify_schema(row)
        if schema == "labeled_dataset" or any(k in row for k in ("direction", "side", "horizon_sec", "horizon_seconds")) and any(k in row for k in ("label", "target", "class")):
            direction = str(_first(row, ("direction", "side"), "")).upper()
            horizon = _first(row, ("horizon_sec", "horizon_seconds", "horizon_s", "horizon"))
            if not direction or horizon is None:
                key = ("label_unkeyable", row.get("_source_index", len(kept)), repr(row))
                dropped["unkeyable_label_kept_uniquely"] += 1
            else:
                key = ("label", round(ts, 4), direction, str(horizon))
        elif schema == "market_trades" or any(k in row for k in ("price", "size", "trade_id")):
            message = row.get("message") if isinstance(row.get("message"), dict) else row
            price = _first(message, ("price", "p", "ap", "bp"))
            size = _first(message, ("size", "q", "as", "bs", "quantity"))
            trade_id = _first(message, ("trade_id", "tradeId", "id"))
            event_type = _first(message, ("event_type", "type"), _first(row, ("event_type", "type"), ""))
            key = ("tick", round(ts, 4), str(event_type), str(price), str(size), str(trade_id))
        else:
            # Only exact payload duplicates are removed for other event types.
            key = ("payload", round(ts, 4), repr(sorted((k, repr(v)) for k, v in row.items() if not k.startswith("_"))))
        if key in seen:
            dropped["duplicate"] += 1
            continue
        seen.add(key)
        kept.append(row)
    return {"records": kept, "input_records": len(kept) + sum(dropped.values()) - dropped["unkeyable_label_kept_uniquely"], "kept_records": len(kept), "dropped_counts": dict(dropped)}


def purged_walk_forward_splits(
    records: Iterable[dict[str, Any]],
    splits: int = 5,
    max_horizon_sec: float = 300.0,
    embargo_sec: float = 60.0,
    min_train: int = 1,
    min_test: int = 1,
) -> dict[str, Any]:
    """Expanding-window splits with horizon purge and post-test embargo.

    Records are sorted by normalized timestamp. For each fold, training records must
    precede test start by at least max_horizon_sec. Any later fold's training data
    also excludes prior test-end embargo intervals. Label realization timestamps,
    when supplied, are checked directly and must not cross the test boundary.
    """
    if splits < 1 or max_horizon_sec < 0 or embargo_sec < 0:
        raise ValueError("invalid_split_parameters")
    rows = [dict(r) for r in records]
    for row in rows:
        if "ts_utc_s" not in row:
            row["ts_utc_s"] = timestamp_from_record(row)[0]
    rows.sort(key=lambda r: float(r["ts_utc_s"]))
    n = len(rows)
    if n < splits + 1:
        return {"status": "REVISE", "reason": "insufficient_rows", "folds": [], "row_count": n}
    times = [float(r["ts_utc_s"]) for r in rows]
    min_t, max_t = times[0], times[-1]
    if max_t <= min_t:
        return {"status": "REVISE", "reason": "zero_time_span", "folds": [], "row_count": n}
    span = max_t - min_t
    block = span / (splits + 1)
    prior_embargoes: list[tuple[float, float]] = []
    folds = []
    for fold in range(splits):
        test_start = min_t + block * (fold + 1)
        test_end = min_t + block * (fold + 2)
        train_indices = []
        test_indices = []
        for idx, row in enumerate(rows):
            ts = float(row["ts_utc_s"])
            if test_start <= ts < test_end:
                test_indices.append(idx)
            elif ts < test_start - max_horizon_sec:
                if any(start <= ts < end for start, end in prior_embargoes):
                    continue
                train_indices.append(idx)
        # If label_end_ts is present, it must resolve before the test begins.
        direct_leakage = []
        for idx in train_indices:
            row = rows[idx]
            label_end = row.get("label_end_ts", row.get("future_ts", row.get("resolved_ts")))
            if label_end is not None:
                try:
                    end_ts = normalize_timestamp(label_end, "label_end_ts")
                except ValueError:
                    direct_leakage.append(idx)
                    continue
                if end_ts > test_start:
                    direct_leakage.append(idx)
        if direct_leakage:
            bad = set(direct_leakage)
            train_indices = [idx for idx in train_indices if idx not in bad]
        train_times = [times[i] for i in train_indices]
        test_times = [times[i] for i in test_indices]
        overlap = any(
            rows[i].get("label_end_ts", rows[i].get("future_ts", rows[i].get("resolved_ts"))) is not None
            and normalize_timestamp(rows[i].get("label_end_ts", rows[i].get("future_ts", rows[i].get("resolved_ts"))), "label_end_ts") > test_start
            for i in train_indices
        )
        fold_result = {
            "fold": fold + 1,
            "train_indices": train_indices,
            "test_indices": test_indices,
            "train_count": len(train_indices),
            "test_count": len(test_indices),
            "test_start_ts": test_start,
            "test_end_ts": test_end,
            "train_max_ts": max(train_times) if train_times else None,
            "test_min_ts": min(test_times) if test_times else None,
            "purge_window_sec": max_horizon_sec,
            "embargo_sec": embargo_sec,
            "direct_label_boundary_leakage": len(direct_leakage),
            "boundary_leakage": overlap,
            "status": "PASS" if len(train_indices) >= min_train and len(test_indices) >= min_test and not overlap else "REVISE",
        }
        folds.append(fold_result)
        prior_embargoes.append((test_end, test_end + embargo_sec))
    overall = "PASS" if len(folds) == splits and all(f["status"] == "PASS" for f in folds) else "REVISE"
    return {
        "schema": "purged_walk_forward_split_v1",
        "status": overall,
        "row_count": n,
        "splits_requested": splits,
        "max_horizon_sec": max_horizon_sec,
        "embargo_sec": embargo_sec,
        "folds": folds,
        "warning": "PASS means temporal split invariants passed; it does not establish predictive edge or justify promotion.",
    }
