"""Authenticated Delta Exchange India v2 client.

Default behavior is non-trading. Order methods require explicit caller-side
authorization and are never exposed through the dashboard.
"""
from __future__ import annotations
import json, os, time
from typing import Any
from urllib.parse import urlencode
import requests
from execution.delta_signer import sign

class DeltaAuthClient:
    PROD = "https://api.india.delta.exchange"
    DEMO = "https://cdn-ind.testnet.deltaex.org"

    def __init__(self, environment: str | None = None, timeout: float = 10.0):
        # Explicit argument wins, then DELTA_ENV. If neither is set, honor the
        # existing DELTA_API_BASE host instead of silently defaulting to demo.
        selected = environment or os.getenv("DELTA_ENV")
        if selected is None:
            configured_base = os.getenv("DELTA_API_BASE", "").rstrip("/")
            if configured_base == self.PROD:
                selected = "prod"
            elif configured_base == self.DEMO:
                selected = "demo"
            else:
                selected = "demo"
        env = selected.lower()
        if env not in {"demo", "prod"}:
            raise ValueError("DELTA_ENV must be demo or prod")
        self.environment = env
        self.base_url = self.PROD if env == "prod" else self.DEMO
        self.api_key = os.getenv("DELTA_API_KEY", "")
        self.api_secret = os.getenv("DELTA_API_SECRET", "")
        self.timeout = timeout

    def _headers(self, method: str, path: str, params: dict[str, Any] | None, body: str):
        if not self.api_key or not self.api_secret:
            raise RuntimeError("Delta credentials are not configured")
        query = urlencode(sorted((params or {}).items()), doseq=True)
        ts = str(int(time.time()))
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "btc-fisher-trader/1.1",
            "api-key": self.api_key,
            "signature": sign(self.api_secret, method, ts, path, query, body),
            "timestamp": ts,
        }

    def request(self, method: str, path: str, params=None, payload=None):
        body = "" if payload is None else json.dumps(payload, separators=(",", ":"))
        headers = self._headers(method, path, params, body)
        r = requests.request(
            method.upper(), self.base_url + path, params=params,
            data=body if body else None, headers=headers, timeout=self.timeout,
        )
        r.raise_for_status()
        result = r.json()
        if isinstance(result, dict) and result.get("success") is False:
            raise RuntimeError(f"Delta API error: {result}")
        return result

    def get_open_orders(self, symbol: str | None = None):
        params = {"product_symbol": symbol} if symbol else None
        return self.request("GET", "/v2/orders", params=params)

    def get_position(self, symbol: str = "BTCUSD", product_id: int | None = None):
        params = {"product_id": int(product_id)} if product_id is not None else {"product_symbol": symbol}
        return self.request("GET", "/v2/positions", params=params)

    def place_order(self, payload: dict[str, Any]):
        return self.request("POST", "/v2/orders", payload=payload)

    def place_bracket(self, payload: dict[str, Any]):
        return self.request("POST", "/v2/orders/bracket", payload=payload)

    def get_order(self, order_id: int):
        return self.request("GET", f"/v2/orders/{int(order_id)}")

    def get_order_leverage(self, product_id: int):
        return self.request("GET", f"/v2/products/{int(product_id)}/orders/leverage")
