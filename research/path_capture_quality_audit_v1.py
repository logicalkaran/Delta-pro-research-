"""Read-only capture quality audit for sampled BTC microstructure paths."""
from __future__ import annotations

import json
import math
import os
import re
import subprocess
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TAPE = ROOT / "data/processed/live_microstructure_features_v1.jsonl"
LABELED = ROOT / "data/processed/live_microstructure_labeled_v1.jsonl"
RAW = ROOT / "data/raw"
STUDY = ROOT / "data/processed/path_aware_event_exit_study_v1.json"
OUT = ROOT / "data/processed/path_capture_quality_audit_v1.json"
FEATURE_FIELDS = ("ts", "mid", "spread", "spread_bps", "imb5", "imb10", "depth5_ratio", "depth10_ratio", "delta5", "delta30", "delta60", "ret5", "ret30", "ret60", "cvd", "cvd_slope30", "regime", "fresh", "trade_samples")
FEED_REQUIRED = {
    "trades": ("t/ts", "p", "s", "sy"),
    "ob_l1": ("ts", "bp", "ap", "bs", "as", "sy"),
    "ob_l2": ("ts", "b", "a", "sy"),
}


def number(value):
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def read_jsonl(path):
    rows, bad = [], 0
    if not path.exists():
        return rows, bad
    with path.open(errors="replace") as stream:
        for line in stream:
            try:
                row = json.loads(line)
                if isinstance(row, dict):
                    rows.append(row)
                else:
                    bad += 1
            except (json.JSONDecodeError, TypeError):
                bad += 1
    return rows, bad


def gap_stats(timestamps):
    """Summarize positive gaps between sorted, finite timestamp values."""
    values = sorted(x for raw in timestamps if (x := number(raw)) is not None)
    gaps = sorted(b - a for a, b in zip(values, values[1:]) if b > a)

    def quantile(q):
        if not gaps:
            return None
        rank = (len(gaps) - 1) * q
        lo, hi = math.floor(rank), math.ceil(rank)
        return gaps[lo] + (gaps[hi] - gaps[lo]) * (rank - lo)

    return {
        "timestamp_count": len(values), "positive_gap_count": len(gaps),
        "median_seconds": quantile(.5), "p90_seconds": quantile(.9),
        "p95_seconds": quantile(.95), "p99_seconds": quantile(.99),
        "max_seconds": max(gaps) if gaps else None,
        "over_1_second": sum(g > 1 for g in gaps),
        "over_2_seconds": sum(g > 2 for g in gaps),
        "over_5_seconds": sum(g > 5 for g in gaps),
    }


def timestamp_audit(rows, key="ts", price_key=None):
    raw_ts = [number(row.get(key)) for row in rows]
    good = [t for t in raw_ts if t is not None]
    sorted_ts = sorted(good)
    positive_mids = 0
    invalid_mids = 0
    if price_key:
        for row in rows:
            price = number(row.get(price_key))
            if price is None or price <= 0:
                invalid_mids += 1
            else:
                positive_mids += 1
    return {
        "row_count": len(rows), "valid_timestamp_rows": len(good),
        "invalid_or_missing_timestamp_rows": len(rows) - len(good),
        "duplicate_timestamp_rows": len(good) - len(set(good)),
        "out_of_order_adjacent_pairs": sum(a is not None and b is not None and b < a for a, b in zip(raw_ts, raw_ts[1:])),
        "start_ts": sorted_ts[0] if sorted_ts else None,
        "end_ts": sorted_ts[-1] if sorted_ts else None,
        "invalid_mid_rows": invalid_mids if price_key else None,
        "positive_mid_rows": positive_mids if price_key else None,
        "gaps": gap_stats(good),
    }


def epoch_seconds(value):
    """Normalize seconds or microseconds epoch values; preserve unknowns as None."""
    x = number(value)
    if x is None:
        return None
    if x > 1e14:
        x /= 1e6
    elif x > 1e11:
        x /= 1e3
    return x


def classify_timestamp_sources(feature_rows, raw_rows):
    raw_messages = [r.get("message", r) for r in raw_rows if isinstance(r.get("message", r), dict)]
    event = [epoch_seconds(m.get("t", m.get("ts"))) for m in raw_messages]
    received = []
    for row in raw_rows:
        try:
            received.append(datetime.fromisoformat(row["received_at"].replace("Z", "+00:00")).timestamp())
        except (KeyError, TypeError, ValueError):
            pass
    feat = [number(r.get("ts")) for r in feature_rows]
    feat = [x for x in feat if x is not None]
    event = [x for x in event if x is not None]
    return {
        "feature_tape_ts": "processing/state-update wall-clock epoch seconds from updated_at_epoch; not an exchange event timestamp",
        "raw_received_at": "local collector receive time in UTC ISO-8601",
        "raw_message_t_or_ts": "venue-supplied message event timestamp (Delta schema uses microseconds); event/exchange timestamp, not local receive time",
        "raw_event_timestamp_rows": len(event), "raw_received_timestamp_rows": len(received),
        "feature_timestamp_rows": len(feat),
        "median_receive_minus_message_event_seconds": _median([r-e for r, e in zip(received, event)]) if len(received) == len(event) else None,
        "receive_minus_event_is_one_way_latency": False,
        "receive_minus_event_note": "This offset can be negative because venue and local clocks may be skewed; it is not a trustworthy one-way latency estimate without clock synchronization.",
        "feature_minus_event_overlap_comparable": False,
        "classification_basis": "delta_collector.websocket_client.save_raw wraps each message with received_at; delta_collector.microstructure._event_ts consumes message t or ts for event-window calculations; feature tape reads data/live_microstructure_state.json updated_at_epoch.",
    }


def _median(values):
    values = sorted(values)
    if not values:
        return None
    n = len(values)
    return values[n // 2] if n % 2 else (values[n // 2 - 1] + values[n // 2]) / 2


def raw_inventory():
    inventory = []
    for path in sorted(RAW.rglob("*.jsonl")):
        rows, bad = read_jsonl(path)
        event_times, receive_times = [], []
        types, fields, missing = Counter(), set(), Counter()
        for row in rows:
            msg = row.get("message", row)
            if not isinstance(msg, dict):
                continue
            kind = str(msg.get("type", "unknown")); types[kind] += 1; fields.update(msg)
            ts = epoch_seconds(msg.get("t", msg.get("ts")))
            if ts is not None:
                event_times.append(ts)
            if isinstance(row.get("received_at"), str):
                try:
                    receive_times.append(datetime.fromisoformat(row["received_at"].replace("Z", "+00:00")).timestamp())
                except (TypeError, ValueError):
                    pass
            for field in FEED_REQUIRED.get(kind, ()):
                if field == "t/ts":
                    present = msg.get("t") is not None or msg.get("ts") is not None
                else:
                    present = msg.get(field) is not None
                if not present:
                    missing[f"{kind}.{field}"] += 1
        inventory.append({
            "file": str(path.relative_to(ROOT)), "rows": len(rows), "invalid_json_rows": bad,
            "event_timestamp_start": min(event_times) if event_times else None,
            "event_timestamp_end": max(event_times) if event_times else None,
            "receive_timestamp_start": min(receive_times) if receive_times else None,
            "receive_timestamp_end": max(receive_times) if receive_times else None,
            "message_types": dict(types), "message_fields_union": sorted(fields),
            "missing_required_feed_fields": dict(missing),
            "timestamp_basis": "message t/ts is venue-supplied event time; wrapper received_at is local receive time",
        })
    return inventory


def overlap(a, b):
    if None in (a.get("start_ts"), a.get("end_ts"), b.get("start_ts"), b.get("end_ts")):
        return {"overlap": False, "overlap_seconds": 0.0}
    seconds = max(0.0, min(a["end_ts"], b["end_ts"]) - max(a["start_ts"], b["start_ts"]))
    return {"overlap": seconds > 0, "overlap_seconds": seconds}


def process_commandlines():
    try:
        result = subprocess.run(["ps", "-eo", "pid,etime,args"], capture_output=True, text=True, timeout=5, check=False)
        lines = []
        for line in result.stdout.splitlines():
            parts = line.strip().split(None, 2)
            args = parts[2] if len(parts) == 3 else ""
            if re.match(r"python(?:\d+(?:\.\d+)*)?\s+(?:research/live_microstructure_feature_tape_v1\.py|-m\s+delta_collector\.websocket_client)(?:\s|$)", args):
                lines.append(line.strip())
        return {"available": result.returncode == 0, "matching_processes": lines}
    except (OSError, subprocess.SubprocessError) as exc:
        return {"available": False, "error": type(exc).__name__, "matching_processes": []}


def build_report():
    features, feature_bad = read_jsonl(TAPE)
    labeled, labeled_bad = read_jsonl(LABELED)
    tape_audit = timestamp_audit(features, price_key="mid")
    label_audit = timestamp_audit(labeled, price_key="mid")
    raw = raw_inventory()
    raw_ranges = [{"file": x["file"], "event_time_overlap_feature_tape": overlap(tape_audit, {"start_ts": x["event_timestamp_start"], "end_ts": x["event_timestamp_end"]}),
                  "event_time_overlap_labeled_capture": overlap(label_audit, {"start_ts": x["event_timestamp_start"], "end_ts": x["event_timestamp_end"]})} for x in raw]
    study = {}
    if STUDY.exists():
        try:
            d = json.loads(STUDY.read_text())
            study = d.get("capture_audit", {})
        except (OSError, json.JSONDecodeError):
            pass
    current_raw = [x for x in raw if x["file"] == "data/raw/delta_btc_raw.jsonl"]
    current_overlap = raw_ranges[[x["file"] for x in raw].index("data/raw/delta_btc_raw.jsonl")] if current_raw else None
    return {
        "schema": "path_capture_quality_audit_v1", "research_only": True, "real_orders": False,
        "source_files": ["research/path_aware_event_exit_study_v1.py", "research/live_microstructure_feature_tape_v1.py", "research/live_microstructure_forward_worker_v1.py", "research/live_microstructure_labeler_v1.py", "delta_collector/websocket_client.py", "delta_collector/live_state.py", "delta_collector/microstructure.py", "delta_collector/config.py", "data/processed/live_microstructure_features_v1.jsonl", "data/processed/live_microstructure_labeled_v1.jsonl", "data/raw/**/*.jsonl"],
        "jsonl_parse_errors": {"feature_tape": feature_bad, "labeled": labeled_bad},
        "feature_tape": tape_audit, "labeled_capture": label_audit,
        "feature_fields_missing_row_count": {field: sum(field not in row for row in features) for field in FEATURE_FIELDS},
        "raw_feed_inventory": raw, "raw_overlap_by_file": raw_ranges,
        "capture_overlap_summary": {
            "current_raw_file_overlaps_full_feature_tape": bool(current_overlap and current_overlap["event_time_overlap_feature_tape"]["overlap"]),
            "current_raw_file_overlaps_labeled_study_capture": bool(current_overlap and current_overlap["event_time_overlap_labeled_capture"]["overlap"]),
            "path_study_reported_raw_feed_overlap_with_labeled_capture": study.get("raw_feed_overlap"),
            "interpretation": "A raw WebSocket file overlaps the newest derived feature-tape interval, but available raw retention does not overlap the labeled historical study capture. Thus the study's path remains a derived feature-tape sample, not a raw-tick reconstruction.",
        },
        "timestamp_classification": classify_timestamp_sources(features, read_jsonl(RAW / "delta_btc_raw.jsonl")[0]),
        "running_process_commandlines": process_commandlines(),
        "cadence_assessment": {
            "configured_feature_snapshot_interval_seconds": 1.0,
            "observed_gap_distribution": tape_audit["gaps"],
            "interpretation": "Nominal one-second polling yields near-one-second derived rows; the feature state can repeat between feed events, and long-tail gaps remain capable of hiding fast moves.",
        },
        "event_driven_sampling_feasibility": {
            "possible_as_research_only_sidecar_without_production_changes": True,
            "basis": "The existing raw WebSocket JSONL contains trades, L1 and L2 message types and local receive timestamps; current raw capture overlaps the latest feature-tape interval. A separate offline/observer process can derive candidate triggers and retain event-time plus receive-time observations.",
            "limitations": ["Current raw file is bounded and rolls over by truncation; it does not preserve the historical labeled study interval.", "Raw capture alone is not a validated complete archive and should not be used to claim event completeness.", "Any event-driven observer must preserve a periodic baseline and log capture loss, timestamps, triggers, and cooldowns to make sampling bias auditable."],
        },
        "safe_recommendations": [
            "Keep the current one-second tape as the baseline/control and quantify missingness before interpreting sub-second path behavior.",
            "For research only, run an independent observer over the already captured feed and emit extra snapshots on predeclared market-state changes, with a short cooldown and a periodic baseline; do not connect it to strategy or execution.",
            "Record venue event time and local receive time separately in the research output, plus sequence/capture gaps and feed-field validity.",
            "Compare candidate triggers against the periodic baseline using matched periods and capture-quality strata before making any cadence claim.",
        ],
    }


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(build_report(), indent=2, sort_keys=True) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
