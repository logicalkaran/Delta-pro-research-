"""Delta order/position reconciliation.

Never assumes a local submission succeeded; queries Delta for authoritative state.
"""
from __future__ import annotations
from dataclasses import dataclass
from execution.delta_client_private import DeltaAuthClient

@dataclass(frozen=True)
class Reconciliation:
    orders: object
    position: object

class DeltaReconciler:
    def __init__(self, client=None):
        self.client = client or DeltaAuthClient()

    def reconcile(self, symbol: str = "BTCUSD") -> Reconciliation:
        return Reconciliation(
            orders=self.client.get_open_orders(symbol),
            position=self.client.get_position(symbol),
        )

    def find_client_order(self, orders_payload, client_order_id: str):
        rows = orders_payload.get("result", []) if isinstance(orders_payload, dict) else []
        for row in rows:
            if row.get("client_order_id") == client_order_id:
                return row
        return None
