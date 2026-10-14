#!/usr/bin/env python3
"""Bounded Delta Exchange India public market-data harvest for offline research.

Collects public product/ticker/order-book data and OHLCV series for price,
mark, funding and open interest. It never reads credentials or calls private,
order, leverage, margin, or transfer endpoints. No background loop is started.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode
import requests

BASE_URL = "https://api.india.delta.exchange"
MAX_CANDLES = 2000
RESOLUTION_SECONDS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}
SERIES = (("price", "1m", "{symbol}"), ("price", "5m", "{symbol}"),
          ("price", "1h", "{symbol}"), ("mark", "1m", "MARK:{symbol}"),
          ("funding", "1h", "FUNDING:{symbol}"), ("open_interest", "1h", "OI:{symbol}"))

class HarvestError(RuntimeError):
    pass


def _get_json(session: Any, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    url = BASE_URL + path
    response = session.get(url, params=params, headers={"Accept": "application/json", "User-Agent": "btc-fisher-public-research/1.0"}, timeout=12)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise HarvestError(f"Delta public endpoint returned unsuccessful schema: {path}")
    return payload


def _result_list(payload: dict[str, Any], endpoint: str) -> list[dict[str, Any]]:
    rows = payload.get("result")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise HarvestError(f"Unexpected list schema from {endpoint}")
    return rows


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, separators=(",", ":"), sort_keys=True, allow_nan=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try: os.unlink(tmp_name)
        except OSError: pass
        raise


def harvest(symbols: list[str], output_dir: Path, *, session: Any = requests,
            now_ts: int | None = None, max_candles: int = MAX_CANDLES) -> dict[str, Any]:
    if not symbols or any(not s or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in s.upper()) for s in symbols):
        raise ValueError("symbols must be non-empty exchange symbols")
    if not 1 <= max_candles <= MAX_CANDLES:
        raise ValueError(f"max_candles must be 1..{MAX_CANDLES}")
    symbols = list(dict.fromkeys(s.upper() for s in symbols))
    now_ts = int(time.time()) if now_ts is None else int(now_ts)
    collected_at = datetime.fromtimestamp(now_ts, timezone.utc).isoformat()
    # Broad metadata snapshot is retained for cross-product filtering, but only
    # compact product/ticker fields are kept to limit storage and noise.
    products_all = _result_list(_get_json(session, "/v2/products"), "/v2/products")
    tickers_all = _result_list(_get_json(session, "/v2/tickers"), "/v2/tickers")
    product_fields = ("id", "symbol", "contract_type", "state", "underlying_asset", "quoting_asset", "settling_asset", "contract_value", "contract_unit_currency", "tick_size", "lot_size", "initial_margin", "maintenance_margin", "maker_commission_rate", "taker_commission_rate", "funding_method", "product_specs", "trading_status", "default_leverage", "max_leverage_notional")
    ticker_fields = ("symbol", "product_id", "contract_type", "timestamp", "time", "open", "high", "low", "close", "mark_price", "spot_price", "funding_rate", "oi", "oi_value", "oi_value_usd", "volume", "turnover", "turnover_usd", "quotes", "mark_basis", "ltp_change_24h", "product_trading_status")
    # Keep a compact exchange-wide universe snapshot (perpetuals, dated
    # futures, options and spot where listed), then retain selected symbols
    # separately for direct strategy use.
    universe_products = [{k: row[k] for k in product_fields if k in row} for row in products_all]
    universe_tickers = [{k: row[k] for k in ticker_fields if k in row} for row in tickers_all]
    products = [row for row in universe_products if str(row.get("symbol", "")).upper() in symbols]
    tickers = [row for row in universe_tickers if str(row.get("symbol", "")).upper() in symbols]
    if len(products) != len(symbols):
        found = {str(x.get("symbol", "")).upper() for x in products}
        raise HarvestError("No product metadata for requested symbol(s): " + ",".join(s for s in symbols if s not in found))
    orderbooks: dict[str, Any] = {}
    candle_sets: dict[str, Any] = {}
    failures: list[dict[str, str]] = []
    for symbol in symbols:
        try:
            orderbooks[symbol] = _get_json(session, f"/v2/l2orderbook/{symbol}")
        except Exception as exc:
            failures.append({"dataset": f"orderbook:{symbol}", "error_type": type(exc).__name__, "message": str(exc)[:120]})
        for dataset, resolution, template in SERIES:
            series_symbol = template.format(symbol=symbol)
            seconds = RESOLUTION_SECONDS[resolution]
            end = now_ts
            start = end - seconds * max_candles
            try:
                payload = _get_json(session, "/v2/history/candles", {"resolution": resolution, "symbol": series_symbol, "start": start, "end": end})
                rows = _result_list(payload, f"candles:{series_symbol}:{resolution}")
                # Canonical sort/deduplicate timestamps. Raw candle values are retained.
                by_time: dict[int, dict[str, Any]] = {}
                for row in rows:
                    t = row.get("time", row.get("timestamp"))
                    if t is None: continue
                    try: ti = int(t)
                    except (TypeError, ValueError): continue
                    if start <= ti <= end: by_time[ti] = row
                candle_sets[f"{symbol}|{dataset}|{resolution}"] = {
                    "symbol": series_symbol, "resolution": resolution, "start": start, "end": end,
                    "count": len(by_time), "candles": [by_time[t] for t in sorted(by_time)],
                }
            except Exception as exc:
                failures.append({"dataset": f"candles:{series_symbol}:{resolution}", "error_type": type(exc).__name__, "message": str(exc)[:120]})
    data = {
        "schema_version": 1,
        "collected_at": collected_at,
        "exchange": "Delta Exchange India",
        "base_url": BASE_URL,
        "symbols": symbols,
        "data_scope": "PUBLIC_MARKET_DATA_ONLY",
        "products": products,
        "tickers": tickers,
        "market_universe_products": universe_products,
        "market_universe_tickers": universe_tickers,
        "orderbooks": orderbooks,
        "candle_sets": candle_sets,
        "failures": failures,
        "authority": {"research_only": True, "paper_only": True, "real_orders": False, "private_account_data_used": False, "mutation_endpoints_used": False},
    }
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    data["integrity"] = {"sha256_before_integrity_field": hashlib.sha256(canonical).hexdigest(), "candle_series": len(candle_sets), "candle_rows": sum(v["count"] for v in candle_sets.values())}
    filename = "delta_public_market_" + datetime.fromtimestamp(now_ts, timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".json"
    path = output_dir / filename
    _atomic_json(path, data)
    return {"path": str(path), "collected_at": collected_at, "symbols": symbols, "product_count": len(products), "ticker_count": len(tickers), "market_universe_product_count": len(universe_products), "market_universe_ticker_count": len(universe_tickers), "orderbook_count": len(orderbooks), "candle_series": len(candle_sets), "candle_rows": data["integrity"]["candle_rows"], "failures": failures, "sha256": data["integrity"]["sha256_before_integrity_field"], "research_only": True, "real_orders": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", default="BTCUSD", help="comma-separated Delta product symbols")
    parser.add_argument("--output-dir", default="data/raw/delta_public_market")
    parser.add_argument("--max-candles", type=int, default=MAX_CANDLES, help="per series, max 2000; 1m/5m/1h windows vary by resolution")
    args = parser.parse_args()
    try:
        result = harvest([s.strip() for s in args.symbols.split(",") if s.strip()], Path(args.output_dir), max_candles=args.max_candles)
        print(json.dumps(result, indent=2))
        return 0 if result["candle_series"] else 2
    except Exception as exc:
        print(json.dumps({"status": "FAILED_CLOSED", "error_type": type(exc).__name__, "message": str(exc)[:180], "real_orders": False}, indent=2))
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
