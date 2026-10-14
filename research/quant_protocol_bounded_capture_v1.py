"""Run one bounded Delta public-WebSocket capture plus aligned state sidecar.

Research-only. Maximum runtime 5 minutes, maximum raw uncompressed payload 8 MB,
maximum aligned output 20 MB. Does not call private APIs or place orders.
"""
from __future__ import annotations
import hashlib, json, signal, threading, time, uuid
from datetime import datetime, timezone
from pathlib import Path

from delta_collector import websocket_client_v5 as collector
from delta_collector.partitioned_raw_writer import PartitionedGzipJSONLWriter
from research.quant_protocol_aligned_capture_v1 import extract_snapshot, finite

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "data/live_microstructure_state.json"
OUT = ROOT / "data/raw/quant_protocol_bounded"
MAX_SECONDS = 300
MAX_RAW_BYTES = 8_000_000
MAX_ALIGNED_BYTES = 20_000_000
MAX_PART_BYTES = 2_000_000
POLL_SECONDS = 0.20
SESSION = "quant_bounded_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:6]
STOP = threading.Event()

def stop_handler(signum, frame):
    STOP.set()
    collector.shutdown(signum, frame)

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    aligned_path = OUT / (SESSION + "_aligned.jsonl")
    manifest_path = OUT / (SESSION + "_manifest.json")
    raw_dir = OUT / (SESSION + "_raw")
    raw_writer = PartitionedGzipJSONLWriter(raw_dir, session_id=SESSION, max_part_bytes=MAX_PART_BYTES)
    raw_bytes = 0
    raw_cap_hit = False
    original_save_raw = collector.save_raw

    def bounded_save_raw(message):
        nonlocal raw_bytes, raw_cap_hit
        record = {"received_at": collector.utc_now(), "message": message,
                  "session_id": SESSION, "research_only": True, "real_orders": False}
        encoded = json.dumps(record, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n"
        size = len(encoded.encode("utf-8"))
        if raw_bytes + size > MAX_RAW_BYTES:
            raw_cap_hit = True
            stop_handler(signal.SIGTERM, None)
            return
        raw_writer.write(record)
        raw_bytes += size

    collector.save_raw = bounded_save_raw
    signal.signal(signal.SIGINT, stop_handler)
    signal.signal(signal.SIGTERM, stop_handler)
    start_epoch = time.time()
    start_mono = time.monotonic()
    last_state_ts = None
    sequence = 0
    accepted = rejected = 0
    state_advanced = False
    error = None
    aligned_bytes = 0
    thread = threading.Thread(target=collector.run, name="bounded_delta_public_collector", daemon=True)
    thread.start()
    try:
        with aligned_path.open("x", encoding="utf-8") as f:
            while not STOP.is_set() and time.monotonic() - start_mono < MAX_SECONDS:
                if STATE.exists():
                    try:
                        state = json.loads(STATE.read_text(encoding="utf-8"))
                        ts = finite(state.get("updated_at_epoch"))
                        now = time.time()
                        if ts is not None and ts > 0 and now - ts <= 2.0 and ts != last_state_ts:
                            state_advanced = True
                            row = extract_snapshot(state, SESSION, sequence + 1, now)
                            row["capture_session"] = SESSION
                            encoded = json.dumps(row, separators=(",", ":"), allow_nan=False) + "\n"
                            n = len(encoded.encode("utf-8"))
                            if aligned_bytes + n > MAX_ALIGNED_BYTES:
                                break
                            f.write(encoded)
                            f.flush()
                            aligned_bytes += n
                            sequence += 1
                            last_state_ts = ts
                            if row["quality_status"] == "PASS":
                                accepted += 1
                            else:
                                rejected += 1
                    except (OSError, ValueError, TypeError) as exc:
                        error = type(exc).__name__ + ": " + str(exc)[:160]
                time.sleep(POLL_SECONDS)
    finally:
        STOP.set()
        try:
            collector.shutdown(signal.SIGTERM, None)
        except Exception:
            pass
        thread.join(timeout=8)
        collector.save_raw = original_save_raw
        raw_writer.close()

    aligned_hash = hashlib.sha256(aligned_path.read_bytes()).hexdigest() if aligned_path.exists() else None
    parts = []
    if raw_dir.exists():
        for p in sorted(raw_dir.glob("*.jsonl.gz")):
            parts.append({"path": str(p.relative_to(ROOT)), "bytes": p.stat().st_size})
    manifest = {
        "session_id": SESSION,
        "status": "CAPTURE_COMPLETE" if sequence else "NO_FRESH_SOURCE_STATE",
        "started_epoch": start_epoch, "elapsed_seconds": round(time.monotonic()-start_mono, 2),
        "raw_uncompressed_bytes": raw_bytes, "raw_cap_bytes": MAX_RAW_BYTES,
        "raw_cap_hit": raw_cap_hit, "raw_records": raw_writer.records_written,
        "raw_parts": parts,
        "aligned_path": str(aligned_path.relative_to(ROOT)),
        "aligned_rows": sequence, "aligned_bytes": aligned_bytes,
        "aligned_sha256": aligned_hash,
        "quality_pass_rows": accepted, "quality_reject_rows": rejected,
        "source_state_advanced": state_advanced,
        "collector_thread_alive_after_shutdown": thread.is_alive(),
        "error": error,
        "timestamp_warning": "state_updated_epoch is local state-refresh time, not exchange-native book-event time",
        "research_only": True, "real_orders": False, "live_trading_enabled": False,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0 if sequence and state_advanced else 2

if __name__ == "__main__":
    raise SystemExit(main())
