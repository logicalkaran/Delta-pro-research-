#!/usr/bin/env python3
"""Read-only source inventory for BTC research datasets; writes one audit JSON artifact."""
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = DATA / "processed" / "btc_dataset_lineage_manifest_v1.json"
TIME_KEYS = ("ts", "timestamp", "timestamp_ms", "timestamp_ns", "ts_ms",
             "time", "time_ms", "exchange_timestamp", "received_at",
             "local_timestamp", "created_at", "event_time")
MAX_SAMPLE_SCHEMAS = 5

def parse_epoch(value):
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            try:
                value = float(value)
            except ValueError:
                return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    if value > 1e17:
        value /= 1e9
    elif value > 1e14:
        value /= 1e6
    elif value > 1e11:
        value /= 1e3
    if value <= 0:
        return None
    return value

def utc(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat() if epoch is not None else None

def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def inspect_file(path):
    digest = hashlib.sha256()
    rows = invalid = duplicate_lines = 0
    seen_lines = set()
    top_keys = Counter()
    schemas = Counter()
    time_field_counts = Counter()
    timestamp_values = []
    session_counts = Counter()
    event_type_counts = Counter()
    nested_message_rows = 0
    with path.open("rb") as stream:
        for raw in stream:
            digest.update(raw)
            if not raw.strip():
                continue
            line_hash = hashlib.sha256(raw).hexdigest()
            if line_hash in seen_lines:
                duplicate_lines += 1
            else:
                seen_lines.add(line_hash)
            try:
                row = json.loads(raw)
            except (ValueError, UnicodeDecodeError):
                invalid += 1
                continue
            rows += 1
            if not isinstance(row, dict):
                schemas["<non-object>"] += 1
                continue
            keys = sorted(row.keys())
            top_keys.update(keys)
            schemas[json.dumps(keys, separators=(",", ":"))] += 1
            if row.get("session_id") is not None:
                session_counts[str(row["session_id"])] += 1
            for key in ("type", "event", "event_type"):
                if isinstance(row.get(key), str):
                    event_type_counts[f"{key}={row[key]}"] += 1
            candidates = [(k, row.get(k)) for k in TIME_KEYS if row.get(k) is not None]
            message = row.get("message")
            if isinstance(message, dict):
                nested_message_rows += 1
                for k in ("ts", "timestamp", "time", "lts"):
                    if message.get(k) is not None:
                        candidates.append((f"message.{k}", message[k]))
            parsed = None
            parsed_key = None
            for key, value in candidates:
                epoch = parse_epoch(value)
                if epoch is not None:
                    time_field_counts[key] += 1
                    if parsed is None:
                        parsed, parsed_key = epoch, key
            if parsed is not None:
                timestamp_values.append((parsed, parsed_key))
    epochs = [item[0] for item in timestamp_values]
    diffs = [b - a for a, b in zip(epochs, epochs[1:])]
    distinct_epochs = set(epochs)
    date_counts = Counter(
        datetime.fromtimestamp(t, timezone.utc).date().isoformat() for t in epochs
    )
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": digest.hexdigest(),
        "nonblank_records": rows,
        "invalid_json_lines": invalid,
        "exact_duplicate_lines_after_first_occurrence": duplicate_lines,
        "timestamped_records": len(epochs),
        "timestamp_field_counts": dict(time_field_counts),
        "first_timestamp_utc": utc(min(epochs)) if epochs else None,
        "last_timestamp_utc": utc(max(epochs)) if epochs else None,
        "utc_date_record_counts": dict(date_counts),
        "unique_timestamp_count": len(distinct_epochs),
        "extra_rows_at_repeated_timestamps": len(epochs) - len(distinct_epochs),
        "negative_adjacent_timestamp_steps": sum(x < 0 for x in diffs),
        "adjacent_gaps_over_5s": sum(x > 5 for x in diffs),
        "adjacent_gaps_over_30s": sum(x > 30 for x in diffs),
        "maximum_positive_adjacent_gap_seconds": round(max(diffs), 6) if diffs else 0,
        "session_id_counts": dict(session_counts),
        "top_level_key_counts": dict(top_keys),
        "schema_fingerprints": [
            {"keys_json": schema, "rows": count}
            for schema, count in schemas.most_common(MAX_SAMPLE_SCHEMAS)
        ],
        "event_type_counts": dict(event_type_counts),
        "rows_with_nested_message": nested_message_rows,
    }

def main():
    if not DATA.is_dir():
        raise SystemExit(f"Data directory not found: {DATA}")
    paths = sorted(p for p in DATA.rglob("*.jsonl") if p.is_file())
    records = [inspect_file(path) for path in paths]
    hashes = Counter(record["sha256"] for record in records)
    duplicate_hash_groups = {}
    for record in records:
        if hashes[record["sha256"]] > 1:
            duplicate_hash_groups.setdefault(record["sha256"], []).append(record["path"])
    result = {
        "schema": "btc_dataset_lineage_manifest_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "data/**/*.jsonl",
        "source_files_scanned": len(records),
        "total_records": sum(r["nonblank_records"] for r in records),
        "total_invalid_json_lines": sum(r["invalid_json_lines"] for r in records),
        "exact_duplicate_file_groups": list(duplicate_hash_groups.values()),
        "files": records,
        "lineage_policy": {
            "source_files_modified": False,
            "credentials_or_account_data_read": False,
            "same_hash_means_byte_identical": True,
            "timestamp_overlap_is_not_proof_of_parent_child_lineage": True,
            "missing_session_id_means_unknown_provenance": True,
            "row_count_is_not_independent_sample_count": True,
            "duplicate_timestamps_may_be_valid_for_multi-side_or_multi-horizon_labels": True,
        },
        "validation_status": "INVENTORY_ONLY_NOT_A_PROMOTION_OR_VALIDATION_RESULT",
        "limitations": [
            "This inventory does not infer unverified source-to-derived lineage.",
            "Timestamp selection is heuristic for heterogeneous schemas; inspect field counts before use.",
            "Exact duplicate lines and byte-identical files are reported, not automatically removed.",
            "No row is deleted or rewritten; original files remain unchanged.",
            "Temporal split purge must be derived from the actual label horizon and applied by a separate validated experiment."
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    temp = OUT.with_suffix(OUT.suffix + ".tmp")
    temp.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(OUT)
    print("WROTE", OUT.relative_to(ROOT), "bytes", OUT.stat().st_size)
    print("JSONL files:", len(records))
    print("Total records:", result["total_records"])
    print("Invalid JSON lines:", result["total_invalid_json_lines"])
    print("Byte-identical duplicate file groups:", len(duplicate_hash_groups))
    for group in duplicate_hash_groups.values():
        print("DUPLICATE_FILE_GROUP", " | ".join(group))
    print("STATUS", result["validation_status"])

if __name__ == "__main__":
    main()
