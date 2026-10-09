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

    def assert_consistent(self, orders_payload, position_payload, expected_client_order_id=None):
        """Return a fail-closed reconciliation result; never assumes local success."""
        orders = orders_payload.get("result", []) if isinstance(orders_payload, dict) else []
        position = position_payload.get("result", position_payload) if isinstance(position_payload, dict) else position_payload
        if expected_client_order_id and self.find_client_order(orders_payload, expected_client_order_id) is None:
            return False, "ORDER_NOT_CONFIRMED"
        if position is None:
            return False, "POSITION_STATE_UNAVAILABLE"
        if isinstance(orders, list):
            for row in orders:
                if not isinstance(row, dict):
                    return False, "INVALID_ORDER_STATE"
                if row.get("client_order_id") and len(str(row["client_order_id"])) > 64:
                    return False, "INVALID_CLIENT_ORDER_ID"
        return True, "RECONCILED"
