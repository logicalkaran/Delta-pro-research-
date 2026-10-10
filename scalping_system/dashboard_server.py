"""Production-style static web/API gateway for the BTC paper platform."""
from __future__ import annotations

import hmac
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
sys.path.insert(0, str(ROOT))

HOST = os.environ.get("BTC_DASHBOARD_HOST", "127.0.0.1")
PORT = int(os.environ.get("BTC_DASHBOARD_PORT", "8790"))
TOKEN = os.environ.get("BTC_DASHBOARD_TOKEN", "")
MAX_BODY = 64 * 1024
FISHER_CACHE = {"at": 0.0, "value": None}


def _json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return default


def _monthly_fisher():
    now = time.time()
    if FISHER_CACHE["value"] is not None and now - FISHER_CACHE["at"] < 60:
        return FISHER_CACHE["value"]
    try:
        from execution.delta_history import DeltaDailyHistory
        from data.market_state import aggregate_daily_to_monthly
        from strategy.signal import FisherSignalEngine

        daily = DeltaDailyHistory(symbol="BTCUSD").fetch(
            start=int(now) - 3 * 365 * 86400, end=int(now)
        )
        monthly = aggregate_daily_to_monthly(daily)
        out = [FisherSignalEngine().process(c) for c in monthly[:-1]]
        out = [x for x in out if x]
        if not out:
            value = None
        else:
            x = out[-1]
            value = {
                "month": x.month,
                "fisher": x.fisher,
                "trigger": x.trigger,
                "bullish_cross": x.bullish_cross,
            }
    except Exception:
        value = None
    FISHER_CACHE.update(at=now, value=value)
    return value


def state():
    from paper.paper_engine import PaperEngine
    from platform_health import health

    p = PaperEngine(symbol="BTCUSD")
    live = _json(ROOT / "data/live_market_state.json", {})
    candles = _json(ROOT / "data/live_candles.json", [])
    microstructure = _json(ROOT / "data/live_microstructure_state.json", {})
    predictive_levels = _json(ROOT / "data/processed/predictive_levels_live.json", {})
    paper_v3 = _json(ROOT / "data/processed/live_execution_paper_v3_summary.json", {})
    live_gate = None
    try:
        from live_readiness_gate import evaluate
        live_gate = evaluate()
    except Exception:
        live_gate = {"locked": True, "eligible": False, "live_execution": False}
    return {
        "project": "btc_fisher_trader",
        "read_only": True,
        "live_orders_enabled": False,
        "health": health(),
        "live_market": live,
        "candles": candles[-300:],
        "microstructure": microstructure,
        "predictive_levels": predictive_levels,
        "paper_v3": paper_v3,
        "live_gate": live_gate,
        "paper": {
            "position": None if p.position is None else {
                "side": p.position.side,
                "quantity": p.position.quantity,
                "entry_price": p.position.entry_price,
            },
            "orders": len(p.orders),
        },
        "monthly_fisher": {
            "latest": _monthly_fisher(),
            "parameters": {"source": "HL2", "length": 10, "alpha": 0.33, "beta": 0.67},
        },
        "signal": {
            "decision": "WAIT",
            "confidence": 0.0,
            "reason_codes": ["RESEARCH_ONLY"],
        },
    }


class H(BaseHTTPRequestHandler):
    server_version = "BTCDeltaDesk/1.1"
    sys_version = ""

    def _auth(self):
        if not TOKEN:
            return True
        supplied = self.headers.get("Authorization", "")
        return hmac.compare_digest(supplied, f"Bearer {TOKEN}")

    def _send(self, code, body, typ="text/plain; charset=utf-8"):
        if isinstance(body, str):
            raw = body.encode("utf-8")
        else:
            raw = body
        self.send_response(code)
        self.send_header("Content-Type", typ)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; manifest-src 'self'; worker-src 'self'",
        )
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(raw)

    def _request_path(self):
        return urlsplit(self.path).path

    def _protected(self):
        return self._request_path() in {"/api/state", "/health", "/ready"}

    def do_HEAD(self):
        return self.do_GET()

    def do_GET(self):
        path = self._request_path()
        if self._protected() and not self._auth():
            return self._send(401, "unauthorized")
        if path == "/api/state":
            try:
                return self._send(200, json.dumps(state(), separators=(",", ":")), "application/json")
            except Exception:
                return self._send(503, '{"status":"unavailable"}', "application/json")
        if path == "/health":
            from platform_health import health
            result = health()
            return self._send(200 if result["status"] == "OK" else 503,
                              json.dumps(result, separators=(",", ":")), "application/json")
        if path == "/ready":
            from platform_health import health
            result = health()
            ready = result["status"] == "OK"
            return self._send(200 if ready else 503,
                              json.dumps({"ready": ready, "status": result["status"]},
                                         separators=(",", ":")), "application/json")

        rel = path.lstrip("/") or "index.html"
        if rel == "service-worker.js":
            rel = "sw.js"
        target = (WEB / rel).resolve()
        try:
            target.relative_to(WEB.resolve())
        except ValueError:
            return self._send(403, "forbidden")
        if not target.is_file():
            target = WEB / "index.html"
        types = {
            ".html": "text/html; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".svg": "image/svg+xml",
        }
        try:
            body = target.read_bytes()
        except OSError:
            return self._send(404, "not found")
        return self._send(200, body, types.get(target.suffix, "text/plain; charset=utf-8"))

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length > MAX_BODY:
            return self._send(413, "payload too large")
        return self._send(405, "method not allowed")

    def do_PUT(self):
        return self._send(405, "method not allowed")

    def do_PATCH(self):
        return self._send(405, "method not allowed")

    def do_DELETE(self):
        return self._send(405, "method not allowed")

    def log_message(self, *_args):
        return


if __name__ == "__main__":
    loopback = HOST in {"127.0.0.1", "::1", "localhost"}
    if not loopback and len(TOKEN) < 32:
        raise SystemExit("Refusing non-loopback bind without BTC_DASHBOARD_TOKEN >= 32 characters.")
    if TOKEN and len(TOKEN) < 32:
        raise SystemExit("BTC_DASHBOARD_TOKEN must be at least 32 characters.")
    print(f"BTC Delta web app: http://{HOST}:{PORT}")
    class ReusableHTTPServer(ThreadingHTTPServer):
        allow_reuse_address = True
    server = ReusableHTTPServer((HOST, PORT), H)
    server.daemon_threads = True
    server.serve_forever(poll_interval=0.5)
