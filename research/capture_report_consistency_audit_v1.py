"""Cross-check capture-session counters against the independent raw integrity audit.

Offline only. A raw audit PASS is not promoted to a session PASS when the collector's
own report records sequence gaps, backfill failures, malformed rows, or count drift.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


COUNT_MAP = {
    "binance_aggTrade": ("binance_aggtrade", "rows"),
    "binance_depthUpdate": ("binance_depth", "rows"),
    "delta_ob_l2": ("delta_l2", "rows"),
}


def evaluate(capture: dict, integrity: dict) -> dict:
    blockers: list[str] = []
    counts = capture.get("counts")
    if not isinstance(counts, dict):
        blockers.append("capture report missing counts object")
        counts = {}

    for key in ("sequence_gaps", "aggtrade_gaps_detected", "aggtrade_backfill_failures", "bad_rows"):
        if key not in counts:
            blockers.append(f"capture report missing required counter {key}")
            continue
        value = counts[key]
        try:
            value = int(value)
        except (TypeError, ValueError):
            blockers.append(f"capture counter {key} is invalid")
            continue
        if value < 0:
            blockers.append(f"capture counter {key} is negative")
        elif value > 0:
            blockers.append(f"capture report records {value} {key}")

    if integrity.get("verdict") != "PASS":
        blockers.append(f"raw integrity verdict is {integrity.get('verdict', 'missing')!r}, not PASS")

    for capture_key, (audit_group, audit_key) in COUNT_MAP.items():
        if capture_key not in counts:
            blockers.append(f"capture report missing comparable count {capture_key}")
            continue
        try:
            captured = int(counts[capture_key])
            audited = int(integrity[audit_group][audit_key])
        except (KeyError, TypeError, ValueError):
            blockers.append(f"cannot compare {capture_key} with raw audit")
            continue
        if captured != audited:
            blockers.append(f"count mismatch for {capture_key}: capture={captured}, audit={audited}")

    if not capture.get("research_only", True) is True:
        blockers.append("capture report is not explicitly research_only")
    if capture.get("real_orders", False) is not False:
        blockers.append("capture report does not explicitly confirm real_orders=false")

    return {
        "schema": "capture_report_consistency_audit_v1",
        "research_only": True,
        "real_orders": False,
        "raw_integrity_verdict": integrity.get("verdict", "MISSING"),
        "capture_sequence_gaps": counts.get("sequence_gaps"),
        "blockers": blockers,
        "verdict": "PASS" if not blockers else "FAIL_CLOSED",
        "meaning": (
            "Capture counters and raw audit agree under the checked invariants."
            if not blockers else
            "Do not treat this capture as clean for research; resolve or explicitly explain every blocker."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-report", required=True, type=Path)
    parser.add_argument("--integrity-audit", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    capture = json.loads(args.capture_report.read_text(encoding="utf-8"))
    integrity = json.loads(args.integrity_audit.read_text(encoding="utf-8"))
    result = evaluate(capture, integrity)
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if result["verdict"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
