"""Paper-only adapter for deterministic async execution simulation.

This adapter is deliberately not imported by the live execution controller and has
no exchange client, credentials, network access, or persistent production side effects.
"""
from __future__ import annotations
from decimal import Decimal
from typing import Any
from execution.async_order_simulator import AsyncOrderSimulator, PerpetualLedger

D = Decimal

class AsyncSimulationAdapter:
    def __init__(self, latency_ms: int = 50, ledger: PerpetualLedger | None = None):
        self.execution = AsyncOrderSimulator(latency_ms=latency_ms)
        self.ledger = ledger if ledger is not None else PerpetualLedger()
        self.research_events: list[dict[str, Any]] = []

    def update_book(self, bids, asks, now_ms: int) -> None:
        self.execution.update_book(bids, asks, now_ms)

    def submit_intent(self, side: str, price: Decimal | str, quantity: Decimal | str,
                      now_ms: int):
        """Submit a theoretical order; exchange acknowledgement is delayed in simulation."""
        order = self.execution.submit(side, price, quantity, now_ms)
        self.research_events.append({"kind": "INTENT_ACCEPTED_FOR_SIMULATION",
                                     "at_ms": now_ms, "order_id": order.order_id})
        return order

    def request_cancel(self, order_id: int, now_ms: int) -> None:
        self.execution.cancel(order_id, now_ms)

    def on_trade(self, price, quantity, aggressor: str, now_ms: int):
        return self.execution.trade(price, quantity, aggressor, now_ms)

    def on_mark_index(self, mark_price, index_price, now_ms: int) -> dict[str, Any]:
        self.execution.update_mark_index(mark_price, index_price, now_ms)
        return self.ledger.margin_snapshot(mark_price)

    def settle_funding(self, now_ms: int, boundary_rate=None, mark_price=None):
        """Settle using the caller-supplied boundary mark when available."""
        rows = self.ledger.settle_through(now_ms, rate_at_boundary=boundary_rate,
                                          mark_price=mark_price)
        self.research_events.extend({"kind": "FUNDING_SETTLEMENT", **row} for row in rows)
        return rows

    def snapshot(self) -> dict[str, Any]:
        return {"mode": "RESEARCH_SIMULATION_ONLY", "live_orders_enabled": False,
                "execution": self.execution.snapshot(), "research_events": list(self.research_events)}
