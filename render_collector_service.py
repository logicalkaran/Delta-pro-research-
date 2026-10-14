"""Render web-service supervisor for the existing read-only Delta public feed.

This is not an exchange execution service. It launches the repository's existing
collector as a child process and exposes liveness/readiness endpoints. Render Free
is best-effort only: filesystem persistence and continuous uptime are not guaranteed.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"  # Render Free has no persistent disk; do not imply otherwise.
STATE_FILES = (
    DATA / "live_market_state.json",
    DATA / "live_microstructure_state.json",
)
MAX_STALE_SECONDS = max(5, int(os.environ.get("MAX_STALE_SECONDS", "20")))
CHECK_INTERVAL_SECONDS = max(2, int(os.environ.get("HEALTH_CHECK_INTERVAL_SECONDS", "5")))
ALERT_COOLDOWN_SECONDS = max(60, int(os.environ.get("ALERT_COOLDOWN_SECONDS", "300")))
PORT = int(os.environ.get("PORT", "10000"))
WEBHOOK = os.environ.get("ALERT_WEBHOOK_URL", "").strip()
_child: subprocess.Popen | None = None
_shutdown = threading.Event()
_state_lock = threading.Lock()
_status = {
    "started_at": time.time(),
    "collector_pid": None,
    "collector_restarts": 0,
    "last_collector_start": None,
    "last_exit_code": None,
    "last_error": None,
    "last_alert_at": 0.0,
    "last_alert_key": None,
}


def latest_state() -> dict:
    candidates = []
    for path in STATE_FILES:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            stamp = data.get("updated_at_epoch", data.get("updated_at"))
            if stamp is None:
                continue
            stamp = float(stamp)
            if stamp > 1e11:  # micro/nanosecond exchange timestamps are not local receive time
                continue
            if stamp > 0:
                candidates.append((stamp, path.name, data))
        except (OSError, ValueError, TypeError):
            continue
    if not candidates:
        return {"ok": False, "reason": "NO_VALID_STATE_FILE", "age_seconds": None}
    stamp, name, data = max(candidates, key=lambda x: x[0])
    age = max(0.0, time.time() - stamp)
    book = data.get("order_book") or {}
    price = data.get("mid_price") or book.get("mid_price") or data.get("last_price")
    try:
        price = float(price)
        price_ok = price > 0
    except (TypeError, ValueError):
        price_ok = False
    fresh = age <= MAX_STALE_SECONDS
    return {
        "ok": bool(fresh and price_ok),
        "reason": "OK" if fresh and price_ok else ("STALE_STATE" if not fresh else "INVALID_PRICE"),
        "state_file": name,
        "age_seconds": round(age, 3),
        "max_stale_seconds": MAX_STALE_SECONDS,
        "mid_or_last_price_present": price_ok,
        "symbol": data.get("symbol", "BTCUSD"),
        "timestamp_kind": "local_receive_or_processing_time_not_exchange_event_time",
    }


def status_payload() -> dict:
    with _state_lock:
        base = dict(_status)
    child = _child
    base["collector_running"] = bool(child and child.poll() is None)
    base["feed"] = latest_state()
    base["service_mode"] = "READ_ONLY_PUBLIC_MARKET_DATA"
    base["live_orders_enabled"] = False
    base["storage_mode"] = "EPHEMERAL_UNLESS_EXTERNAL_PERSISTENT_STORAGE_CONFIGURED"
    return base


def alert(event: str, details: dict) -> None:
    if not WEBHOOK:
        return
    now = time.time()
    key = event + ":" + str(details.get("reason", ""))
    with _state_lock:
        if key == _status["last_alert_key"] and now - _status["last_alert_at"] < ALERT_COOLDOWN_SECONDS:
            return
        _status["last_alert_key"] = key
        _status["last_alert_at"] = now
    payload = json.dumps({
        "text": "Delta BTCUSD read-only collector alert",
        "event": event,
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "details": details,
        "live_orders_enabled": False,
    }).encode()
    try:
        req = Request(WEBHOOK, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(req, timeout=4) as response:
            if response.status >= 300:
                raise RuntimeError("webhook returned non-success status")
    except Exception as exc:
        with _state_lock:
            _status["last_error"] = "ALERT_DELIVERY_FAILED:" + type(exc).__name__


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print("HTTP " + (fmt % args), flush=True)

    def do_GET(self):
        if self.path not in ("/", "/healthz", "/readyz", "/status"):
            self.send_json(404, {"ok": False, "error": "NOT_FOUND"})
            return
        payload = status_payload()
        if self.path == "/healthz":
            # Liveness: process responds; an external monitor must check /readyz too.
            self.send_json(200, {"ok": True, "service": "delta-readonly-collector"})
        elif self.path == "/readyz":
            ready = payload["collector_running"] and payload["feed"]["ok"]
            self.send_json(200 if ready else 503, payload)
        else:
            self.send_json(200, payload)

    def send_json(self, code: int, payload: dict):
        body = json.dumps(payload, separators=(",", ":"), default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def supervise_collector():
    delay = 2
    while not _shutdown.is_set():
        start = time.time()
        try:
            child = subprocess.Popen(
                [sys.executable, "-m", "delta_collector.websocket_client"],
                cwd=str(ROOT), env=os.environ.copy(),
            )
            global _child
            _child = child
            with _state_lock:
                _status["collector_pid"] = child.pid
                _status["last_collector_start"] = start
            print(f"COLLECTOR_STARTED pid={child.pid}", flush=True)
            while not _shutdown.is_set():
                rc = child.poll()
                feed = latest_state()
                if not feed["ok"]:
                    alert("FEED_NOT_READY", feed)
                if rc is not None:
                    with _state_lock:
                        _status["last_exit_code"] = rc
                        _status["collector_restarts"] += 1
                        _status["last_error"] = "COLLECTOR_EXITED"
                    alert("COLLECTOR_EXITED", {"exit_code": rc})
                    break
                _shutdown.wait(CHECK_INTERVAL_SECONDS)
            if _shutdown.is_set() and child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=3)
                break
            # Reset backoff only after a sustained healthy run.
            if time.time() - start > 300 and latest_state()["ok"]:
                delay = 2
            else:
                delay = min(60, delay * 2)
        except Exception as exc:
            with _state_lock:
                _status["last_error"] = type(exc).__name__ + ":" + str(exc)[:200]
                _status["collector_restarts"] += 1
            alert("SUPERVISOR_EXCEPTION", {"error": type(exc).__name__})
        _shutdown.wait(delay)


def monitor_feed():
    stale_was_alerted = False
    while not _shutdown.wait(CHECK_INTERVAL_SECONDS):
        feed = latest_state()
        if not feed["ok"]:
            alert("FEED_NOT_READY", feed)
            stale_was_alerted = True
        elif stale_was_alerted:
            alert("FEED_RECOVERED", feed)
            stale_was_alerted = False


def stop(signum, frame):
    _shutdown.set()


def main():
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    DATA.mkdir(parents=True, exist_ok=True)
    threading.Thread(target=supervise_collector, name="collector-supervisor", daemon=True).start()
    threading.Thread(target=monitor_feed, name="feed-monitor", daemon=True).start()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    server.timeout = 1
    print(f"HTTP_HEALTH_SERVER port={PORT} orders_enabled=false", flush=True)
    try:
        while not _shutdown.is_set():
            server.handle_request()
    finally:
        server.server_close()
        _shutdown.set()


if __name__ == "__main__":
    main()
