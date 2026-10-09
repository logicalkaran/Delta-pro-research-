"""Safety-gated Delta execution adapter.

This adapter defaults to dry-run. It refuses production orders unless the
live-readiness gate is explicitly satisfied and a second execution switch is
set outside the web application.
"""
from __future__ import annotations
import os, time
from execution.delta_client_private import DeltaAuthClient

class LiveExecutionBlocked(RuntimeError):
    pass

class DeltaExecutor:
    def __init__(self, client=None):
        self.client = client or DeltaAuthClient()

    def submit_market(self, *, product_id: int, product_symbol: str,
                      side: str, size: int, client_order_id: str,
                      reduce_only: bool = False, dry_run: bool = True):
        if side not in {"buy", "sell"}:
            raise ValueError("side must be buy or sell")
        if size <= 0:
            raise ValueError("size must be positive")
        if len(client_order_id) > 32:
            raise ValueError("client_order_id must be <= 32 characters")
        payload = {
            "product_id": product_id,
            "product_symbol": product_symbol,
            "size": size,
            "side": side,
            "order_type": "market_order",
            "client_order_id": client_order_id,
            "reduce_only": reduce_only,
        }
        if dry_run:
            return {"dry_run": True, "payload": payload}
        if os.getenv("BTC_LIVE_EXECUTION", "").lower() != "true":
            raise LiveExecutionBlocked("BTC_LIVE_EXECUTION is not enabled")
        from execution.live_execution_gate import require
        require()
        if self.client.environment != "prod":
            raise LiveExecutionBlocked("production execution requires DELTA_ENV=prod")
        return self.client.place_order(payload)

    def submit_market_with_bracket(self, *, product_id: int, product_symbol: str,
                                    side: str, size: int, client_order_id: str,
                                    stop_price: float, stop_limit_price: float,
                                    take_profit_price: float, take_profit_limit_price: float,
                                    dry_run: bool = True):
        if side not in {"buy", "sell"}:
            raise ValueError("side must be buy or sell")
        if size <= 0 or len(client_order_id) > 32:
            raise ValueError("invalid size or client_order_id")
        payload = {
            "product_id": product_id,
            "product_symbol": product_symbol,
            "size": size,
            "side": side,
            "order_type": "market_order",
            "client_order_id": client_order_id,
            "reduce_only": False,
            "bracket_stop_trigger_method": "last_traded_price",
            "bracket_stop_loss_price": str(stop_price),
            "bracket_stop_loss_limit_price": str(stop_limit_price),
            "bracket_take_profit_price": str(take_profit_price),
            "bracket_take_profit_limit_price": str(take_profit_limit_price),
        }
        if dry_run:
            return {"dry_run": True, "payload": payload}
        if os.getenv("BTC_LIVE_EXECUTION", "").lower() != "true":
            raise LiveExecutionBlocked("BTC_LIVE_EXECUTION is not enabled")
        from execution.live_execution_gate import require
        require()
        if self.client.environment != "prod":
            raise LiveExecutionBlocked("production execution requires DELTA_ENV=prod")
        return self.client.place_order(payload)
