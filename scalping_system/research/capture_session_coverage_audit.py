"""Offline receive-time coverage audit for a retained Delta raw JSONL snapshot."""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "data/raw/delta_btc_raw.jsonl"
DEFAULT_OUTPUT = ROOT / "data/processed/capture_session_coverage_audit.json"
SESSION_GAP_SECONDS = 30.0


def normalize_epoch(value):
    """Return (epoch seconds or None, unit classification)."""
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None, "invalid"
    if not math.isfinite(x) or x <= 0:
        return None, "invalid"
    if x >= 1e17:
        return x / 1e9, "nanoseconds"
    if x >= 1e14:
        return x / 1e6, "microseconds"
    if x >= 1e11:
        return x / 1e3, "milliseconds"
    return x, "seconds"


def parse_receive(value):
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except (ValueError, OverflowError, OSError):
        return None


def quote_validity(message):
    try:
        bid, ask = float(message["bp"]), float(message["ap"])
    except (KeyError, TypeError, ValueError):
        return False, False
    if not math.isfinite(bid) or not math.isfinite(ask) or bid <= 0 or ask <= 0:
        return False, False
    if ask < bid:
        return False, True
    return True, False


def percentile(values, q):
    if not values:
        return None
    ordered = sorted(values)
    rank = (len(ordered) - 1) * q
    lo, hi = math.floor(rank), math.ceil(rank)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (rank - lo)


def gap_summary(timestamps):
    values = sorted(timestamps)
    gaps = [b - a for a, b in zip(values, values[1:]) if b > a]
    return {
        "positive_gap_count": len(gaps),
        "median_seconds": percentile(gaps, .5), "p90_seconds": percentile(gaps, .9),
        "p95_seconds": percentile(gaps, .95), "p99_seconds": percentile(gaps, .99),
        "max_seconds": max(gaps) if gaps else None,
        "over_1_second": sum(g > 1 for g in gaps),
        "over_2_seconds": sum(g > 2 for g in gaps),
        "over_5_seconds": sum(g > 5 for g in gaps),
    }


def lag_summary(lags):
    return {"count": len(lags), "median_seconds": percentile(lags, .5),
            "p90_seconds": percentile(lags, .9), "p95_seconds": percentile(lags, .95),
            "p99_seconds": percentile(lags, .99), "min_seconds": min(lags) if lags else None,
            "max_seconds": max(lags) if lags else None,
            "definition": "receive timestamp minus normalized venue event timestamp; clock offset means this is not one-way latency"}


def segment_sessions(receive_times, gap_seconds=SESSION_GAP_SECONDS):
    """Segment sorted receive times whenever adjacent records are > gap_seconds apart."""
    times = sorted(receive_times)
    sessions = []
    for ts in times:
        if not sessions or ts - sessions[-1]["last"] > gap_seconds:
            sessions.append({"first": ts, "last": ts, "row_count": 1})
        else:
            sessions[-1]["last"] = ts
            sessions[-1]["row_count"] += 1
    return [{"first_timestamp": s["first"], "last_timestamp": s["last"],
             "duration_seconds": s["last"] - s["first"], "row_count": s["row_count"]}
            for s in sessions]


def audit(source):
    path = Path(source)
    rows_read = malformed = missing_event = 0
    non_market_rows_without_event_timestamp = 0
    event_timestamp_applicable_rows = 0
    market_data_channels = {"trades", "ob_l1", "ob_l2", "ob_updates"}
    receives = []
    channel_receives = defaultdict(list)
    channel_counts = Counter()
    units = Counter()
    lags = []
    valid_quotes = crossed_quotes = invalid_quotes = 0
    with path.open(encoding="utf-8", errors="replace") as stream:
        for line in stream:
            rows_read += 1
            try:
                wrapper = json.loads(line)
            except (json.JSONDecodeError, TypeError):
                malformed += 1
                continue
            if not isinstance(wrapper, dict) or not isinstance(wrapper.get("message", wrapper), dict):
                malformed += 1
                continue
            message = wrapper.get("message", wrapper)
            channel = str(message.get("type") or "missing")
            channel_counts[channel] += 1
            received = parse_receive(wrapper.get("received_at"))
            if received is not None:
                receives.append(received)
                channel_receives[channel].append(received)
            raw_event = message.get("t") if channel == "trades" else message.get("ts")
            if raw_event is None:
                raw_event = message.get("ts", message.get("t"))
            event, unit = normalize_epoch(raw_event)
            units[unit] += 1
            if channel in market_data_channels:
                event_timestamp_applicable_rows += 1
                if event is None:
                    missing_event += 1
                elif received is not None:
                    lags.append(received - event)
            elif event is None:
                # Subscription acknowledgements and other control messages commonly
                # have no venue event timestamp; report them separately from market data.
                non_market_rows_without_event_timestamp += 1
            if channel == "ob_l1":
                valid, crossed = quote_validity(message)
                valid_quotes += int(valid)
                crossed_quotes += int(crossed)
                invalid_quotes += int(not valid)

    sessions = segment_sessions(receives)
    first, last = (min(receives), max(receives)) if receives else (None, None)
    hours = sum(s["duration_seconds"] for s in sessions) / 3600
    ready = len(sessions) >= 3 and hours >= 6
    per_channel = {}
    for channel in sorted(set(channel_counts) | set(channel_receives)):
        ts = channel_receives[channel]
        per_channel[channel] = {"row_count": channel_counts[channel], "receive_timestamp_count": len(ts),
                                "first_receive_timestamp": min(ts) if ts else None,
                                "last_receive_timestamp": max(ts) if ts else None,
                                "inter_arrival_gaps": gap_summary(ts)}
    return {
        "schema": "capture_session_coverage_audit_v1", "research_only": True, "real_orders": False,
        "source_file": str(path), "file_size_bytes": path.stat().st_size,
        "rotation_note": "The raw collector rotates/truncates at 10 MB. This active file is treated as a snapshot; a single retained file cannot establish older coverage after rotation.",
        "rows_read": rows_read, "malformed_rows": malformed,
        "event_timestamp_applicable_rows": event_timestamp_applicable_rows,
        "missing_event_timestamps": missing_event,
        "non_market_rows_without_event_timestamp": non_market_rows_without_event_timestamp,
        "timestamp_normalization_counts": dict(units),
        "timestamp_normalization": "Epoch event timestamps normalized by magnitude from seconds, milliseconds, microseconds, or nanoseconds to seconds; receive_at parsed as ISO-8601 (naive values treated as UTC).",
        "receive_time_coverage": {"valid_receive_timestamp_rows": len(receives), "first_timestamp": first,
                                  "last_timestamp": last, "total_span_seconds": (last-first) if first is not None else 0.0,
                                  "session_gap_threshold_seconds": SESSION_GAP_SECONDS,
                                  "session_count": len(sessions), "sessions": sessions,
                                  "sum_of_session_durations_hours": hours},
        "per_channel": per_channel, "event_to_receive_lag": lag_summary(lags),
        "quotes": {"valid_quote_count": valid_quotes, "crossed_quote_count": crossed_quotes,
                   "invalid_quote_count": invalid_quotes, "validation": "ob_l1 bid/ask finite and positive; ask >= bid"},
        "readiness": {"verdict": "READY" if ready else "NOT_READY",
                      "multi_session_path_study": "READY" if ready else "NOT_READY",
                      "criteria": "At least 3 distinct receive-time sessions and >=6 total hours summed across sessions.",
                      "sessions_required": 3, "hours_required": 6,
                      "sessions_observed": len(sessions), "hours_observed": hours,
                      "reason": "Coverage threshold met." if ready else "Requires at least 3 sessions and 6 total session-hours; current retained snapshot does not meet both thresholds.",
                      "retention_limitation": "A single retained file cannot establish older coverage after rotation."},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=str(DEFAULT_SOURCE), help="raw JSONL snapshot (default: data/raw/delta_btc_raw.jsonl)")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    report = audit(args.source)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"source_file": report["source_file"], "rows_read": report["rows_read"],
                      "receive_time_coverage": report["receive_time_coverage"],
                      "readiness": report["readiness"]}, indent=2))


if __name__ == "__main__":
    main()
