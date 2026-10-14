#!/usr/bin/env python3
"""Streaming, provenance-aware JSONL manifest builder; read-only on source data."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

try:
    from research.data_hygiene import classify_schema, timestamp_from_record
except ModuleNotFoundError:  # Support direct `python research/dataset_manifest.py` invocation.
    from data_hygiene import classify_schema, timestamp_from_record

ROOT = Path(__file__).resolve().parents[1]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_jsonl(path: Path, root: Path) -> dict:
    digest = hashlib.sha256()
    rows = invalid = missing_ts = inversions = duplicate_records = 0
    categories = Counter()
    timestamp_keys = Counter()
    sessions = Counter()
    seen_payloads = set()
    first_ts = last_ts = None
    min_ts = max_ts = None
    dates = Counter()
    with path.open("rb") as stream:
        for raw in stream:
            digest.update(raw)
            if not raw.strip():
                continue
            try:
                record = json.loads(raw)
            except (json.JSONDecodeError, UnicodeDecodeError):
                invalid += 1
                continue
            rows += 1
            canonical = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            payload_hash = hashlib.sha256(canonical).hexdigest()
            if payload_hash in seen_payloads:
                duplicate_records += 1
            seen_payloads.add(payload_hash)
            if not isinstance(record, dict):
                categories["unknown"] += 1
                missing_ts += 1
                continue
            categories[classify_schema(record)] += 1
            if record.get("session_id") is not None:
                sessions[str(record["session_id"])] += 1
            try:
                ts, key = timestamp_from_record(record)
                timestamp_keys[key] += 1
            except ValueError:
                missing_ts += 1
                continue
            if last_ts is not None and ts < last_ts:
                inversions += 1
            last_ts = ts
            first_ts = ts if first_ts is None else first_ts
            min_ts = ts if min_ts is None else min(min_ts, ts)
            max_ts = ts if max_ts is None else max(max_ts, ts)
            dates[datetime.fromtimestamp(ts, timezone.utc).date().isoformat()] += 1
    problems = []
    if rows == 0:
        problems.append("empty_file")
    if invalid:
        problems.append("invalid_json")
    if missing_ts:
        problems.append("missing_or_invalid_timestamp")
    if inversions:
        problems.append("non_monotonic_timestamp_order")
    if duplicate_records:
        problems.append("duplicate_records")
    status = "PASS" if rows > 0 and not problems else "REVISE"
    return {
        "relative_path": path.relative_to(root).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": digest.hexdigest(),
        "total_records": rows,
        "duplicate_records": duplicate_records,
        "invalid_json_lines": invalid,
        "missing_timestamps": missing_ts,
        "timestamped_records": rows - missing_ts - sum(1 for _ in ()),
        "out_of_order_timestamps": inversions,
        "min_timestamp_utc": datetime.fromtimestamp(min_ts, timezone.utc).isoformat() if min_ts is not None else None,
        "max_timestamp_utc": datetime.fromtimestamp(max_ts, timezone.utc).isoformat() if max_ts is not None else None,
        "utc_date_record_counts": dict(dates),
        "timestamp_fields": dict(timestamp_keys),
        "inferred_schema_types": sorted(categories),
        "schema_record_counts": dict(categories),
        "session_id_record_counts": dict(sessions),
        "integrity_status": status,
        "integrity_errors": problems,
    }


def build_manifest(data_dir: Path, root: Path) -> dict:
    paths = sorted(p for p in data_dir.rglob("*.jsonl") if p.is_file())
    files = [inspect_jsonl(p, root) for p in paths]
    by_hash = {}
    for entry in files:
        by_hash.setdefault(entry["sha256"], []).append(entry["relative_path"])
    duplicate_groups = [group for group in by_hash.values() if len(group) > 1]
    duplicate_members = {p for group in duplicate_groups for p in group}
    for entry in files:
        if entry["relative_path"] in duplicate_members:
            entry["integrity_status"] = "REVISE"
            entry["integrity_errors"] = sorted(set(entry["integrity_errors"] + ["byte_identical_duplicate_file"]))
    return {
        "schema": "btc_dataset_manifest_v2",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "root": str(root),
        "data_dir": str(data_dir),
        "source_files": len(files),
        "total_records": sum(f["total_records"] for f in files),
        "files_pass": sum(f["integrity_status"] == "PASS" for f in files),
        "files_revise": sum(f["integrity_status"] == "REVISE" for f in files),
        "duplicate_file_groups": duplicate_groups,
        "files": files,
        "quarantine_policy": {
            "automatic_moves": False,
            "automatic_deletes": False,
            "revise_files_are_excluded_from_research_by_default": True,
            "quarantine_candidates": [f["relative_path"] for f in files if f["integrity_status"] == "REVISE"],
        },
        "promotion_status": "HOLD_REVISE",
        "note": "File-level PASS is a data hygiene gate only; it does not prove source lineage, independent sessions, or profitable predictive edge.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="data/")
    parser.add_argument("--output", default="data/processed/btc_multisession_manifest_v2.json")
    args = parser.parse_args()
    data_dir = Path(args.data_dir).resolve()
    output = Path(args.output).resolve()
    if not data_dir.is_dir():
        raise SystemExit(f"data directory does not exist: {data_dir}")
    root = ROOT
    manifest = build_manifest(data_dir, root)
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_suffix(output.suffix + ".tmp")
    temp.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(output)
    print(json.dumps({
        "output": str(output),
        "source_files": manifest["source_files"],
        "total_records": manifest["total_records"],
        "files_pass": manifest["files_pass"],
        "files_revise": manifest["files_revise"],
        "duplicate_file_groups": len(manifest["duplicate_file_groups"]),
        "promotion_status": manifest["promotion_status"],
    }, indent=2))


if __name__ == "__main__":
    main()
