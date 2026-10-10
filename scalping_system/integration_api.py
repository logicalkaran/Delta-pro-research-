"""Read-only local API exposing selected BTC/Delta project state to DeltaPro."""
from __future__ import annotations

import csv
import hmac
import json
import os
import sys
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
TOKEN = os.environ.get("BTC_DELTA_BRIDGE_TOKEN", "")
HOST = "127.0.0.1"
PORT = int(os.environ.get("BTC_DELTA_BRIDGE_PORT", "8788"))
ORDERFLOW = ROOT / "data/processed/btc_orderflow_features_v1.csv"
CACHE = {"at": 0.0, "snapshot": None}


def _orderflow():
    if not ORDERFLOW.is_file():
        return {"status": "missing", "latest": None}
    with ORDERFLOW.open(newline="", encoding="utf-8") as handle:
        rows = csv.DictReader(handle)
        last = None
        for row in rows:
            last = row
    if last is None:
        return {"status": "empty", "latest": None}
    try:
        stamp = int(float(last.get("timestamp", "0")))
        if stamp > 10_000_000_000_000:
            stamp //= 1_000_000
        elif stamp > 10_000_000_000:
            stamp //= 1_000
        age = max(0, int(time.time()) - stamp) if stamp else None
    except (TypeError, ValueError):
        age = None
    return {"status": "available", "age_seconds": age, "latest": last}


def _fisher_snapshot():
    from execution.delta_history import DeltaDailyHistory
    from data.market_state import aggregate_daily_to_monthly
    from strategy.signal import FisherSignalEngine

    now = int(time.time())
    daily = DeltaDailyHistory(symbol="BTCUSD").fetch(
        start=now - 3 * 365 * 86400, end=now
    )
    monthly = aggregate_daily_to_monthly(daily)
    current = datetime.now(timezone.utc)
    completed = [
        candle for candle in monthly
        if datetime.fromtimestamp(candle.timestamp, timezone.utc).strftime("%Y-%m")
        != current.strftime("%Y-%m")
    ]
    engine = FisherSignalEngine()
    outputs = [engine.process(candle) for candle in completed]
    outputs = [item for item in outputs if item is not None]
    if not outputs:
        return {"status": "insufficient_history", "latest": None}
    latest = outputs[-1]
    return {
        "status": "available",
        "symbol": "BTCUSD",
        "completed_months": len(completed),
        "latest": {
            "month": latest.month,
            "fisher": latest.fisher,
            "trigger": latest.trigger,
            "bullish_cross": latest.bullish_cross,
        },
        "parameters": {"source": "HL2", "length": 10, "alpha": 0.33, "beta": 0.67},
        "execution": "read_only_no_orders",
    }


def snapshot():
    now = time.time()
    if CACHE["snapshot"] is not None and now - CACHE["at"] < 60:
        return CACHE["snapshot"]
    result = {
        "project": "btc_fisher_trader",
        "read_only": True,
        "live_orders_enabled": False,
        "orderflow": _orderflow(),
    }
    try:
        result["monthly_fisher"] = _fisher_snapshot()
    except Exception as exc:
        result["monthly_fisher"] = {
            "status": "unavailable",
            "error_type": type(exc).__name__,
            "message": str(exc)[:240],
        }
    CACHE.update(at=now, snapshot=result)
    return result


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, payload):
        body = json.dumps(payload, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not TOKEN or not hmac.compare_digest(
            self.headers.get("Authorization", ""), f"Bearer {TOKEN}"
        ):
            return self._send(401, {"error": "unauthorized"})
        if self.path == "/health":
            return self._send(200, {
                "status": "ok", "project": "btc_fisher_trader",
                "read_only": True, "live_orders_enabled": False,
            })
        if self.path == "/snapshot":
            return self._send(200, snapshot())
        return self._send(404, {"error": "not_found"})

    def do_POST(self):
        return self._send(405, {"error": "method_not_allowed"})

    def log_message(self, _format, *_args):
        return


if __name__ == "__main__":
    if len(TOKEN) < 32:
        raise SystemExit("Set BTC_DELTA_BRIDGE_TOKEN to a random value of at least 32 characters.")
    print(f"Read-only BTC/Delta bridge listening on http://{HOST}:{PORT}")
    HTTPServer((HOST, PORT), Handler).serve_forever()
