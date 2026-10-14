"""Aggregate bounded Delta capture sessions without changing production code.

Audits each manifest independently, verifies artifact hashes/limits, and replays
book checksums per session. It never starts collectors or trading processes.
"""
import argparse
import glob
import hashlib
import json
import os
from pathlib import Path

from research.quant_protocol_capture_integrity_v1 import audit as audit_integrity

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_GLOB = "data/raw/quant_protocol_bounded/*_manifest.json"


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def audit_manifests(manifest_paths, root=ROOT):
    sessions = []
    seen_ids = set()
    errors = []
    for raw_manifest_path in sorted(manifest_paths):
        mp = Path(raw_manifest_path)
        if not mp.is_absolute():
            mp = root / mp
        try:
            manifest = json.loads(mp.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append({"manifest": str(mp), "error": f"manifest_read_error:{type(exc).__name__}"})
            continue

        sid = manifest.get("session_id")
        session = {
            "session_id": sid,
            "manifest_path": str(mp.relative_to(root) if mp.is_relative_to(root) else mp),
            "capture_status": manifest.get("status"),
            "elapsed_seconds": manifest.get("elapsed_seconds"),
            "aligned_rows": manifest.get("aligned_rows", 0),
            "quality_pass_rows": manifest.get("quality_pass_rows", 0),
            "quality_reject_rows": manifest.get("quality_reject_rows", 0),
            "raw_records": manifest.get("raw_records", 0),
            "raw_cap_hit": manifest.get("raw_cap_hit", False),
            "raw_parts": [],
            "checks": {},
        }
        if not sid or sid in seen_ids:
            errors.append({"manifest": str(mp), "error": "missing_or_duplicate_session_id", "session_id": sid})
        seen_ids.add(sid)

        elapsed = manifest.get("elapsed_seconds")
        session["checks"]["duration_within_300s"] = isinstance(elapsed, (int, float)) and 0 < elapsed <= 300.5
        session["checks"]["raw_cap_not_hit"] = not manifest.get("raw_cap_hit", False)
        session["checks"]["collector_stopped"] = not manifest.get("collector_thread_alive_after_shutdown", True)
        session["checks"]["source_state_advanced"] = bool(manifest.get("source_state_advanced"))
        session["checks"]["aligned_hash_valid"] = False
        session["checks"]["raw_parts_exist"] = True

        aligned_rel = manifest.get("aligned_path")
        aligned = root / aligned_rel if aligned_rel else None
        if aligned and aligned.is_file():
            actual_hash = sha256_file(aligned)
            session["checks"]["aligned_hash_valid"] = actual_hash == manifest.get("aligned_sha256")
            session["checks"]["aligned_file_within_20mb"] = aligned.stat().st_size <= 20_000_000
        else:
            session["checks"]["aligned_file_within_20mb"] = False
            errors.append({"session_id": sid, "error": "aligned_file_missing"})

        raw_paths = []
        for part in manifest.get("raw_parts", []):
            rel = part.get("path")
            p = root / rel if rel else None
            exists = bool(p and p.is_file())
            session["raw_parts"].append({
                "path": rel,
                "exists": exists,
                "compressed_bytes": p.stat().st_size if exists else None,
            })
            if not exists:
                session["checks"]["raw_parts_exist"] = False
                continue
            raw_paths.append(str(p))
            if p.stat().st_size > 2_000_000:
                errors.append({"session_id": sid, "path": rel, "error": "compressed_part_over_2mb"})

        session["checks"]["raw_uncompressed_cap_respected"] = (
            isinstance(manifest.get("raw_uncompressed_bytes"), (int, float))
            and manifest["raw_uncompressed_bytes"] <= manifest.get("raw_cap_bytes", 8_000_000)
        )
        session["checks"]["aligned_row_accounting"] = (
            session["aligned_rows"] == session["quality_pass_rows"] + session["quality_reject_rows"]
        )

        if raw_paths:
            try:
                integrity = audit_integrity(raw_paths)
                session["integrity"] = {
                    "status": integrity["status"],
                    "book_messages": integrity["orderbook"]["seen"],
                    "checksum_ok": integrity["orderbook"]["checksum_ok"],
                    "checksum_failed": integrity["orderbook"]["checksum_failed"],
                    "sequence_or_reconstruction_errors": integrity["orderbook"]["sequence_or_reconstruction_errors"],
                    "malformed_json": integrity["malformed_json"],
                    "checksum_match_rate": integrity["checksum_match_rate"],
                }
                session["checks"]["book_integrity_pass"] = integrity["status"] == "PASS"
            except Exception as exc:
                session["checks"]["book_integrity_pass"] = False
                errors.append({"session_id": sid, "error": f"integrity_audit_error:{type(exc).__name__}:{str(exc)[:120]}"})
        else:
            session["checks"]["book_integrity_pass"] = False

        session["status"] = "PASS" if all(session["checks"].values()) and session.get("integrity", {}).get("book_messages", 0) > 0 else "INCOMPLETE_OR_FAIL"
        sessions.append(session)

    sessions.sort(key=lambda s: s.get("session_id") or "")
    passed = sum(s["status"] == "PASS" for s in sessions)
    return {
        "schema": "quant_protocol_multisession_audit_v1",
        "manifest_count": len(manifest_paths),
        "sessions_audited": len(sessions),
        "sessions_passed": passed,
        "sessions_not_passed": len(sessions) - passed,
        "overall_status": "PASS" if sessions and passed == len(sessions) and not errors else "MORE_DATA_OR_REPAIR_REQUIRED",
        "sessions": sessions,
        "errors": errors,
        "limitations": [
            "Integrity is evaluated within each captured session only; continuity before the first snapshot and across reconnects is not proven.",
            "A clean capture does not establish predictive value or profitability.",
            "This audit reads artifacts only and never starts a collector, paper trader, or real-order process.",
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("manifests", nargs="*")
    parser.add_argument("--output", default="data/processed/quant_protocol_multisession_audit_v1.json")
    args = parser.parse_args()
    paths = args.manifests or sorted(glob.glob(str(ROOT / MANIFEST_GLOB)))
    if not paths:
        raise SystemExit("No bounded capture manifests found")
    result = audit_manifests(paths)
    out = ROOT / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "sessions"}, indent=2))
    for session in result["sessions"]:
        print(json.dumps({"session_id": session["session_id"], "status": session["status"], "checks": session["checks"]}))
    print("output:", out.relative_to(ROOT))


if __name__ == "__main__":
    main()
