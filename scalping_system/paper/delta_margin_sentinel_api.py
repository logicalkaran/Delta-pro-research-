#!/usr/bin/env python3
"""Single-shot, GET-only Delta Exchange India margin diagnostics.

Requires an API key with Read Data permission. No write endpoints exist in this
module; no order, margin, leverage, or auto-topup mutation is possible here.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from http.client import HTTPSConnection
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

from paper.margin_sentinel_readonly import evaluate_snapshot

ALLOWED_HOSTS = {
    "api.india.delta.exchange": 443,
    "cdn-ind.testnet.deltaex.org": 443,
}
READ_PATHS = {"/v2/positions/margined", "/v2/wallet/balances"}


class DeltaReadOnlyError(RuntimeError):
    pass


def signature(secret: str, method: str, timestamp: str, path: str, query: str = "", body: str = "") -> str:
    prehash = method.upper() + timestamp + path + query + body
    return hmac.new(secret.encode("utf-8"), prehash.encode("utf-8"), hashlib.sha256).hexdigest()


class DeltaReadOnlyClient:
    """Minimal signed REST client with a hard-coded GET endpoint allowlist."""

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        base_url: str = "https://api.india.delta.exchange",
        connection_factory: Callable[..., Any] = HTTPSConnection,
        timeout: float = 8.0,
    ) -> None:
        parsed = urlsplit(base_url)
        if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
            raise ValueError("base_url must be one of the explicitly allowed HTTPS Delta hosts")
        if parsed.path not in ("", "/") or parsed.query or parsed.fragment or parsed.username or parsed.password:
            raise ValueError("base_url must be a bare HTTPS origin without path/query/credentials")
        if not api_key or not api_secret:
            raise ValueError("API key and secret are required")
        self.api_key = api_key
        self.api_secret = api_secret
        self.host = parsed.hostname
        self.port = ALLOWED_HOSTS[self.host]
        self.connection_factory = connection_factory
        self.timeout = timeout

    def get_json(self, path: str) -> dict[str, Any]:
        if path not in READ_PATHS:
            raise ValueError("endpoint is not on the read-only allowlist")
        timestamp = str(int(time.time()))
        headers = {
            "Accept": "application/json",
            "User-Agent": "BTC-Fisher-Margin-Sentinel-ReadOnly/1.0",
            "api-key": self.api_key,
            "signature": signature(self.api_secret, "GET", timestamp, path),
            "timestamp": timestamp,
        }
        conn = self.connection_factory(self.host, self.port, timeout=self.timeout)
        try:
            conn.request("GET", path, headers=headers)
            response = conn.getresponse()
            raw = response.read()
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                if response.status < 200 or response.status >= 300:
                    raise DeltaReadOnlyError(f"Delta GET {path} returned HTTP {response.status} with non-JSON body") from exc
                raise DeltaReadOnlyError(f"Delta GET {path} returned invalid JSON") from exc
            if response.status < 200 or response.status >= 300:
                # Surface only safe diagnostic fields; never include raw account data or headers.
                err = payload.get("error", {}) if isinstance(payload, dict) else {}
                code = err.get("code", payload.get("code", "unknown")) if isinstance(err, dict) else "unknown"
                message = err.get("message", payload.get("message", "")) if isinstance(err, dict) else ""
                raise DeltaReadOnlyError(
                    f"Delta GET {path} returned HTTP {response.status} (code={str(code)[:80]}, message={str(message)[:120]})"
                )
            if not isinstance(payload, dict) or payload.get("success") is not True:
                code = payload.get("error", {}).get("code", "unknown") if isinstance(payload, dict) else "invalid_response"
                raise DeltaReadOnlyError(f"Delta GET {path} reported unsuccessful response ({code})")
            return payload
        finally:
            conn.close()


def wallet_summary(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Return schema/asset diagnostics only; never print account balances."""
    result = payload.get("result")
    if not isinstance(result, list):
        raise DeltaReadOnlyError("wallet response schema mismatch: result is not a list")
    summary = []
    tracked_fields = ("balance", "available_balance", "order_margin", "position_margin", "blocked_margin")
    for row in result:
        if not isinstance(row, dict):
            raise DeltaReadOnlyError("wallet response schema mismatch: row is not an object")
        asset = row.get("asset")
        asset_symbol = asset.get("symbol") if isinstance(asset, dict) else row.get("asset_symbol")
        summary.append({
            "asset": str(asset_symbol or "unknown"),
            "balance_fields_present": [field for field in tracked_fields if row.get(field) is not None],
            "account_values_withheld": True,
        })
    return summary


class AlertJournal:
    """SQLite journal records new/changed diagnostic states; it cannot trigger actions."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self.db = sqlite3.connect(self.path, timeout=5)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS sentinel_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                observed_at TEXT NOT NULL,
                symbol TEXT NOT NULL,
                status TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
        """)
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS sentinel_latest (
                symbol TEXT PRIMARY KEY,
                fingerprint TEXT NOT NULL,
                status TEXT NOT NULL,
                observed_at TEXT NOT NULL
            )
        """)
        self.db.commit()

    def record_changes(self, diagnostics: list[dict[str, Any]]) -> int:
        now = datetime.now(timezone.utc).isoformat()
        inserted = 0
        with self.db:
            for item in diagnostics:
                symbol = str(item.get("symbol", "unknown"))
                status = str(item.get("status", "UNKNOWN"))
                stable = {
                    "symbol": symbol,
                    "status": status,
                    "reasons": item.get("reasons", []),
                    "margin_mode": item.get("margin_mode"),
                }
                fingerprint = hashlib.sha256(
                    json.dumps(stable, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest()
                previous = self.db.execute(
                    "SELECT fingerprint FROM sentinel_latest WHERE symbol=?", (symbol,)
                ).fetchone()
                if previous and previous[0] == fingerprint:
                    continue
                self.db.execute(
                    "INSERT INTO sentinel_events(observed_at,symbol,status,fingerprint,payload_json) VALUES(?,?,?,?,?)",
                    (now, symbol, status, fingerprint, json.dumps(item, sort_keys=True)),
                )
                self.db.execute("""
                    INSERT INTO sentinel_latest(symbol,fingerprint,status,observed_at)
                    VALUES(?,?,?,?)
                    ON CONFLICT(symbol) DO UPDATE SET
                      fingerprint=excluded.fingerprint,status=excluded.status,observed_at=excluded.observed_at
                """, (symbol, fingerprint, status, now))
                inserted += 1
        return inserted

    def close(self) -> None:
        self.db.close()


def load_repo_env() -> None:
    """Load missing variables from the repository .env without printing values."""
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or not key.replace("_", "").isalnum():
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        os.environ.setdefault(key, value)


def main() -> int:
    load_repo_env()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="BTCUSD")
    parser.add_argument("--base-url", choices=sorted(f"https://{h}" for h in ALLOWED_HOSTS), default=None)
    parser.add_argument("--journal", default="data/processed/margin_sentinel_events.sqlite3")
    parser.add_argument("--utilization-threshold", default="0.75")
    parser.add_argument("--liquidation-distance-pct", default="5.0")
    args = parser.parse_args()

    api_key = os.environ.get("DELTA_API_KEY", "")
    api_secret = os.environ.get("DELTA_API_SECRET", "")
    if not api_key or not api_secret:
        print("ERROR: Set DELTA_API_KEY and DELTA_API_SECRET; use a Read Data-only API key.", file=sys.stderr)
        return 2

    journal = None
    try:
        configured_base = args.base_url or os.environ.get("DELTA_API_BASE") or "https://api.india.delta.exchange"
        client = DeltaReadOnlyClient(api_key, api_secret, configured_base)
        positions_payload = client.get_json("/v2/positions/margined")
        positions = positions_payload.get("result")
        if not isinstance(positions, list) or any(not isinstance(p, dict) for p in positions):
            raise DeltaReadOnlyError("positions response schema mismatch")
        # Do not assume API-provided maintenance-margin fields exist. The
        # evaluator marks missing utilization inputs as incomplete metrics.
        selected = [p for p in positions if str(p.get("product_symbol", p.get("symbol", ""))).upper() == args.symbol.upper()]
        if selected:
            diagnostics = evaluate_snapshot(
                selected,
                symbol=args.symbol,
                utilization_threshold=__import__("decimal").Decimal(args.utilization_threshold),
                liquidation_distance_threshold_pct=__import__("decimal").Decimal(args.liquidation_distance_pct),
            )
        else:
            diagnostics = [{
                "symbol": args.symbol.upper(),
                "status": "NO_OPEN_POSITION",
                "reasons": [],
                "action": "ALERT_ONLY_NO_COLLATERAL_TRANSFER",
                "paper_only": True,
                "real_orders": False,
                "note": "No matching open position was returned by the read-only positions endpoint.",
            }]
        wallet = wallet_summary(client.get_json("/v2/wallet/balances"))
        journal_path = Path(args.journal)
        journal_path.parent.mkdir(parents=True, exist_ok=True)
        journal = AlertJournal(journal_path)
        changed = journal.record_changes(diagnostics)
        output = {
            "mode": "READ_ONLY_DIAGNOSTIC",
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "positions": diagnostics,
            "wallet_balances_summary": wallet,
            "new_or_changed_alert_states_recorded": changed,
            "api_permissions_required": ["Read Data"],
            "network_enabled": True,
            "mutation_endpoints_enabled": False,
            "collateral_transfer_enabled": False,
            "real_orders": False,
        }
        print(json.dumps(output, indent=2))
        return 0
    except Exception as exc:
        # Fail closed and avoid emitting secrets, signed headers, or raw account responses.
        print(f"ERROR: read-only sentinel failed closed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    finally:
        if journal is not None:
            journal.close()


if __name__ == "__main__":
    raise SystemExit(main())
