import atexit
import json
import os
import signal
import time
from datetime import datetime, timezone
from pathlib import Path

import websocket

from .config import WS_URL, SYMBOL, CHANNELS, RAW_FILE
from .live_state import update as update_live_state
from .partitioned_raw_writer import PartitionedGzipJSONLWriter

ROOT = Path(__file__).resolve().parents[1]
# Canonical research archive: immutable gzip partitions, rotated by uncompressed bytes.
PARTITION_DIR = ROOT / "data" / "raw" / "gzip_sessions"
# Compatibility mirror for older readers. This file is explicitly a bounded tail, not
# the source of truth; all new raw events are written to PARTITION_DIR first.
RAW_MIRROR_MAX_BYTES = 10_000_000
_PARTITION_WRITER = PartitionedGzipJSONLWriter(PARTITION_DIR)
atexit.register(_PARTITION_WRITER.close)


def _terminate_cleanly(signum, frame):
    # Raising SystemExit triggers atexit, which closes gzip and writes its trailer.
    raise SystemExit(0)


signal.signal(signal.SIGTERM, _terminate_cleanly)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def save_raw(message, receive_epoch_ns=None, receive_mono_ns=None):
    record = {
        "received_at": utc_now(),
        "receive_epoch_ns": time.time_ns() if receive_epoch_ns is None else receive_epoch_ns,
        "receive_mono_ns": time.monotonic_ns() if receive_mono_ns is None else receive_mono_ns,
        "message": message,
    }
    # Archive first. A mirror failure must not prevent durable archival of this event.
    _PARTITION_WRITER.write(record)

    # Keep old JSONL readers working against a bounded, rolling recent-data mirror.
    path = Path(RAW_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n"
    encoded = line.encode("utf-8")
    try:
        if path.exists() and path.stat().st_size + len(encoded) > RAW_MIRROR_MAX_BYTES:
            path.write_text(line, encoding="utf-8")
        else:
            with path.open("a", encoding="utf-8") as fh:
                fh.write(line)
                fh.flush()
    except OSError as exc:
        print(f"[MIRROR WARNING] archive written; compatibility mirror failed: {exc}", flush=True)


def on_open(ws):
    print("[CONNECTED] Delta WebSocket", flush=True)
    for channel in CHANNELS:
        ws.send(json.dumps({"type": "subscribe", "payload": {"channels": [{"name": channel, "symbols": [SYMBOL]}]}}))
        print(f"[SUBSCRIBED] {channel}", flush=True)


def on_message(ws, message):
    try:
        receive_epoch_ns = time.time_ns()
        receive_mono_ns = time.monotonic_ns()
        data = json.loads(message)
        save_raw(data, receive_epoch_ns, receive_mono_ns)
        if data.get("type") in {"trades", "ob_l1", "ob_l2"}:
            update_live_state(data)
    except Exception as exc:
        print(f"[PARSE/ARCHIVE ERROR] {exc}", flush=True)


def on_error(ws, error):
    print(f"[WEBSOCKET ERROR] {error}", flush=True)


def on_close(ws, code, msg):
    print(f"[CLOSED] code={code} message={msg}", flush=True)


def run():
    while True:
        try:
            ws = websocket.WebSocketApp(WS_URL, on_open=on_open, on_message=on_message,
                                        on_error=on_error, on_close=on_close)
            ws.run_forever(ping_interval=20, ping_timeout=10)
        except KeyboardInterrupt:
            break
        except SystemExit:
            raise
        except Exception as exc:
            print(f"[FATAL] {exc}", flush=True)
        time.sleep(5)


if __name__ == "__main__":
    run()
