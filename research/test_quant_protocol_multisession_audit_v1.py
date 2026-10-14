import json
from pathlib import Path

from research.quant_protocol_multisession_audit_v1 import audit_manifests, sha256_file


def test_sha256_file(tmp_path):
    p = tmp_path / "x.bin"
    p.write_bytes(b"abc")
    assert sha256_file(p) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_manifest_with_missing_artifacts_is_not_pass(tmp_path):
    manifest = {
        "session_id": "s1",
        "status": "CAPTURE_COMPLETE",
        "elapsed_seconds": 10,
        "aligned_rows": 1,
        "quality_pass_rows": 1,
        "quality_reject_rows": 0,
        "raw_records": 1,
        "raw_cap_hit": False,
        "collector_thread_alive_after_shutdown": False,
        "source_state_advanced": True,
        "raw_uncompressed_bytes": 100,
        "raw_cap_bytes": 8000000,
        "aligned_path": "data/raw/missing_aligned.jsonl",
        "aligned_sha256": "0" * 64,
        "raw_parts": [{"path": "data/raw/missing.jsonl.gz", "bytes": 100}],
    }
    mp = tmp_path / "manifest.json"
    mp.write_text(json.dumps(manifest))
    result = audit_manifests([str(mp)], root=tmp_path)
    assert result["sessions_audited"] == 1
    assert result["sessions_passed"] == 0
    assert result["overall_status"] == "MORE_DATA_OR_REPAIR_REQUIRED"
    assert result["sessions"][0]["checks"]["raw_parts_exist"] is False
    assert result["sessions"][0]["checks"]["aligned_hash_valid"] is False


def test_duplicate_session_ids_are_flagged(tmp_path):
    paths = []
    for i in range(2):
        p = tmp_path / f"m{i}.json"
        p.write_text(json.dumps({"session_id": "duplicate", "elapsed_seconds": 1, "raw_parts": []}))
        paths.append(str(p))
    result = audit_manifests(paths, root=tmp_path)
    assert any(e["error"] == "missing_or_duplicate_session_id" for e in result["errors"])
    assert result["sessions_passed"] == 0
