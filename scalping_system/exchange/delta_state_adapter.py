"""Strict GET-only Delta Exchange v2 account-state adapter.

Credentials are read from environment variables only. This code path has no
mutation methods; configure API-key read-only permissions separately in Delta's
API management UI. A successful GET does not prove the key lacks trade permissions.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
import time
from typing import Any, Callable, Mapping
from urllib.parse import urlencode, urlsplit

import requests

from execution.delta_signer import sign


@dataclass(frozen=True)
class AccountState:
    available_balance: float | None
    equity: float | None
    maintenance_margin: float | None
    open_interest: float | None
    complete: bool
    missing_fields: tuple[str, ...]
    observed_at_ms: int


class DeltaReadOnlyStateAdapter:
    PROD = "https://api.india.delta.exchange"
    DEMO = "https://cdn-ind.testnet.deltaex.org"
    ALLOWED_PATHS = frozenset({"/v2/wallets", "/v2/positions/margined", "/v2/orders"})
    SIGNATURE_WINDOW_SECONDS = 5
    USER_AGENT = "btc-fisher-trader-readonly/1.0"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        api_secret: str | None = None,
        timeout: float = 8.0,
        transport: Callable[..., Any] | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        selected = (base_url or os.getenv("DELTA_API_BASE") or self.DEMO).rstrip("/")
        if selected not in {self.PROD, self.DEMO}:
            raise ValueError("Delta base URL must match an explicitly supported HTTPS host")
        if urlsplit(selected).scheme != "https":
            raise ValueError("Delta adapter requires HTTPS")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.base_url = selected
        self.api_key = api_key if api_key is not None else os.getenv("DELTA_API_KEY", "")
        self.api_secret = api_secret if api_secret is not None else os.getenv("DELTA_API_SECRET", "")
        self.timeout = float(timeout)
        self._transport = transport or requests.get
        self._clock = clock

    def _headers(self, path: str, query: str, *, timestamp: int | None = None) -> dict[str, str]:
        if path not in self.ALLOWED_PATHS:
            raise ValueError("endpoint is not allowlisted for read-only access")
        if not self.api_key or not self.api_secret:
            raise RuntimeError("Delta read-only credentials are not configured")
        now = int(self._clock())
        stamp = now if timestamp is None else int(timestamp)
        if abs(now - stamp) > self.SIGNATURE_WINDOW_SECONDS:
            raise ValueError("Delta signature timestamp outside the 5-second window")
        signature = sign(self.api_secret, "GET", str(stamp), path, query, "")
        return {
            "Accept": "application/json",
            "User-Agent": self.USER_AGENT,
            "api-key": self.api_key,
            "signature": signature,
            "timestamp": str(stamp),
        }

    def _get(self, path: str, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
        if path not in self.ALLOWED_PATHS:
            raise ValueError("endpoint is not allowlisted for read-only access")
        # Sort and encode once, then sign and request the exact same query string.
        pairs = sorted((str(k), v) for k, v in (params or {}).items() if v is not None)
        query = urlencode(pairs, doseq=True)
        url = self.base_url + path + (("?" + query) if query else "")
        headers = self._headers(path, query)
        try:
            response = self._transport(url, headers=headers, timeout=self.timeout)
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            # Do not propagate request exception text, URL query, headers or credentials.
            raise RuntimeError("Delta read-only request failed (" + type(exc).__name__ + ")") from None
        if not isinstance(payload, dict):
            raise ValueError("Delta response schema invalid: expected object")
        if payload.get("success") is False:
            error = payload.get("error", {})
            code = error.get("code", "API_ERROR") if isinstance(error, dict) else "API_ERROR"
            raise RuntimeError("Delta read-only API rejected request (" + str(code)[:80] + ")")
        return payload

    def get_wallets(self) -> dict[str, Any]:
        return self._get("/v2/wallets")

    def get_positions(self) -> dict[str, Any]:
        return self._get("/v2/positions/margined")

    def get_open_orders(self, symbol: str | None = None) -> dict[str, Any]:
        return self._get("/v2/orders", {"product_symbol": symbol} if symbol else None)

    @staticmethod
    def _rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
        result = payload.get("result", [])
        if isinstance(result, dict):
            result = [result]
        if not isinstance(result, list):
            return []
        return [row for row in result if isinstance(row, dict)]

    def checkpoint_equity_hourly(self, state: AccountState, journal: Any) -> dict[str, Any] | None:
        """Append one authoritative equity anchor per UTC hour; missing equity fails closed."""
        if state.equity is None:
            return None
        hour_bucket = int(state.observed_at_ms) // 3_600_000
        event_id = f"delta-equity-anchor:{hour_bucket}"
        # Idempotent across repeated polls and process restarts.
        for event in journal.replay():
            if event.get("event_id") == event_id:
                return event
        return journal.append(
            event_id, "AUTHORITATIVE_EQUITY_ANCHOR",
            {"equity": state.equity, "observed_at_ms": state.observed_at_ms,
             "source": "delta_read_only_adapter", "anchor_hour_utc": hour_bucket},
            ts_ns=int(state.observed_at_ms) * 1_000_000,
        )

    def account_state(self, *, observed_at_ms: int | None = None) -> AccountState:
        wallets = self.get_wallets()
        positions = self.get_positions()
        wallet_rows = self._rows(wallets)
        position_rows = self._rows(positions)

        def first_numeric(rows: list[dict[str, Any]], keys: tuple[str, ...]) -> float | None:
            for row in rows:
                for key in keys:
                    value = row.get(key)
                    if isinstance(value, bool) or value is None:
                        continue
                    if isinstance(value, (int, float, str)):
                        try:
                            numeric = float(value)
                        except (TypeError, ValueError):
                            continue
                        if numeric == numeric and abs(numeric) != float("inf"):
                            return numeric
            return None

        available = first_numeric(wallet_rows, ("available_balance",))
        equity = first_numeric(wallet_rows, ("equity", "equity_balance"))
        maintenance = first_numeric(
            position_rows + wallet_rows,
            ("maintenance_margin", "maintenance_margin_requirement", "maintenance_margin_required"),
        )
        # Open interest is market/product state and is not inferred from account positions.
        open_interest = None
        # Completeness here describes the required account-risk fields only. Open
        # interest is separate market data and is explicitly not fabricated here.
        missing = tuple(
            name for name, value in (
                ("available_balance", available), ("equity", equity),
                ("maintenance_margin", maintenance),
            ) if value is None
        )
        return AccountState(
            available_balance=available, equity=equity, maintenance_margin=maintenance,
            open_interest=open_interest, complete=not missing, missing_fields=missing,
            observed_at_ms=int(self._clock() * 1000) if observed_at_ms is None else int(observed_at_ms),
        )
