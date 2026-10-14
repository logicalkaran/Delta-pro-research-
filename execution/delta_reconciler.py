"""Delta order/position reconciliation.

Never assumes a local submission succeeded; queries Delta for authoritative state.
This module's validation method is pure and makes no network calls.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from execution.delta_client_private import DeltaAuthClient


@dataclass(frozen=True)
class Reconciliation:
    orders: object
    position: object


class DeltaReconciler:
    def __init__(self, client=None):
        self.client = client if client is not None else DeltaAuthClient()

    def reconcile(self, symbol: str = "BTCUSD") -> Reconciliation:
        return Reconciliation(
            orders=self.client.get_open_orders(symbol),
            position=self.client.get_position(symbol),
        )

    @staticmethod
    def _successful_payload(payload: Any) -> bool:
        return isinstance(payload, dict) and payload.get("success") is not False

    def find_client_order(self, orders_payload, client_order_id: str):
        if not self._successful_payload(orders_payload):
            return None
        rows = orders_payload.get("result")
        if not isinstance(rows, list):
            return None
        for row in rows:
            if isinstance(row, dict) and row.get("client_order_id") == client_order_id:
                return row
        return None

    def assert_consistent(self, orders_payload, position_payload, expected_client_order_id=None):
        """Fail closed on explicit API failures and malformed state payloads."""
        if not self._successful_payload(orders_payload):
            return False, "ORDER_STATE_UNAVAILABLE"
        if not self._successful_payload(position_payload):
            return False, "POSITION_STATE_UNAVAILABLE"

        orders = orders_payload.get("result")
        if not isinstance(orders, list) or any(not isinstance(row, dict) for row in orders):
            return False, "INVALID_ORDER_STATE"

        position = position_payload.get("result")
        if not isinstance(position, (list, dict)):
            return False, "INVALID_POSITION_STATE"
        if isinstance(position, list) and any(not isinstance(row, dict) for row in position):
            return False, "INVALID_POSITION_STATE"

        for row in orders:
            client_order_id = row.get("client_order_id")
            if client_order_id is not None:
                if not isinstance(client_order_id, str) or not client_order_id or len(client_order_id) > 64:
                    return False, "INVALID_CLIENT_ORDER_ID"

        if expected_client_order_id is not None:
            if not isinstance(expected_client_order_id, str) or not expected_client_order_id:
                return False, "INVALID_EXPECTED_CLIENT_ORDER_ID"
            if self.find_client_order(orders_payload, expected_client_order_id) is None:
                return False, "ORDER_NOT_CONFIRMED"

        return True, "RECONCILED"
