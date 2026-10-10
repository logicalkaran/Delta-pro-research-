"""Read-only replay and reconciliation for the paper/shadow event journal.

This module never sends exchange mutations. A potentially orphaned exchange order
is surfaced as CANCEL_REQUIRED and blocks resume; a separate reviewed operator
workflow must handle any real cancellation while live execution remains disabled.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Any

from storage.event_journal import EventJournal

D = Decimal


@dataclass(frozen=True)
class ChildRecovery:
    client_order_id: str
    parent_id: str
    quantity: Decimal
    filled_quantity: Decimal
    remaining_quantity: Decimal
    state: str
    acknowledgement_seen: bool
    reconciliation_required: bool


@dataclass(frozen=True)
class ParentRecovery:
    parent_id: str
    quantity: Decimal
    filled_quantity: Decimal
    remaining_size: Decimal
    children: tuple[ChildRecovery, ...]
    can_resume: bool


class StateReconciler:
    def __init__(self, journal: EventJournal):
        self.journal = journal

    def replay(self, *, open_exchange_client_ids: Iterable[str] | None = None) -> dict[str, ParentRecovery]:
        integrity = self.journal.verify()
        if not integrity.get("valid"):
            raise RuntimeError("journal integrity failure: " + str(integrity.get("reason", "UNKNOWN")))
        events = self.journal.replay()
        open_ids = None if open_exchange_client_ids is None else set(open_exchange_client_ids)
        parents: dict[str, dict[str, Any]] = {}
        children: dict[str, dict[str, Any]] = {}

        for event in events:
            kind, payload = event["event_type"], event["payload"]
            parent_id = payload.get("parent_id")
            if kind == "PARENT_CREATED":
                pid = str(payload["parent_id"])
                qty = D(str(payload["quantity"]))
                if not qty.is_finite() or qty <= 0:
                    raise RuntimeError("invalid parent quantity in journal")
                if pid in parents and parents[pid]["quantity"] != qty:
                    raise RuntimeError("conflicting parent definitions in journal")
                parents.setdefault(pid, {"quantity": qty, "children": set()})
                continue

            cid = payload.get("client_order_id")
            if not cid:
                continue
            if kind == "CHILD_DISPATCHED":
                pid = str(parent_id or "unknown")
                qty = D(str(payload["quantity"]))
                if not qty.is_finite() or qty <= 0:
                    raise RuntimeError("invalid child quantity in journal")
                row = children.setdefault(str(cid), {
                    "parent_id": pid, "quantity": qty, "filled": D("0"),
                    "state": "DISPATCHED", "ack": False, "reconcile": True,
                })
                if row["parent_id"] != pid or row["quantity"] != qty:
                    raise RuntimeError("conflicting child dispatch in journal")
                row["state"] = "DISPATCHED"
                row["reconcile"] = True
                if pid not in parents:
                    parents.setdefault(pid, {"quantity": qty, "children": set(), "inferred": True})
                parents[pid]["children"].add(str(cid))
            elif str(cid) in children:
                row = children[str(cid)]
                if kind == "CHILD_ACKNOWLEDGED":
                    row["ack"] = True
                    row["state"] = "ACKNOWLEDGED"
                    # An acknowledgement is not terminal; do not assume the order is filled/canceled.
                    row["reconcile"] = True
                elif kind in {"CHILD_PARTIAL_FILL", "CHILD_FILLED"}:
                    amount = D(str(payload.get("fill_quantity", "0")))
                    if not amount.is_finite() or amount < 0:
                        raise RuntimeError("invalid fill quantity in journal")
                    row["filled"] += amount
                    if row["filled"] > row["quantity"]:
                        raise RuntimeError("journaled fills exceed child quantity")
                    row["state"] = "FILLED" if kind == "CHILD_FILLED" else "PARTIAL_FILL"
                    # A partial fill does not establish that the residual order is terminal.
                    row["reconcile"] = kind != "CHILD_FILLED"
                elif kind == "CHILD_ACK_DEFERRED_STALE_BOOK":
                    row["state"] = "UNKNOWN"
                    row["reconcile"] = True

        result: dict[str, ParentRecovery] = {}
        for pid, parent in parents.items():
            recovered_children = []
            for cid in sorted(parent["children"]):
                row = children[cid]
                state = row["state"]
                needs_reconcile = bool(row["reconcile"])
                if open_ids is not None and cid in open_ids and not row["ack"]:
                    state = "CANCEL_REQUIRED"
                    needs_reconcile = True
                elif open_ids is not None and cid not in open_ids and state in {"DISPATCHED", "ACKNOWLEDGED", "UNKNOWN", "PARTIAL_FILL"}:
                    # Absence from open orders is not proof of a fill/cancel/reject.
                    state = "UNKNOWN"
                    needs_reconcile = True
                recovered_children.append(ChildRecovery(
                    client_order_id=cid, parent_id=pid, quantity=row["quantity"],
                    filled_quantity=row["filled"], remaining_quantity=max(D("0"), row["quantity"] - row["filled"]),
                    state=state, acknowledgement_seen=row["ack"], reconciliation_required=needs_reconcile,
                ))
            filled = sum((child.filled_quantity for child in recovered_children), D("0"))
            remaining = max(D("0"), parent["quantity"] - filled)
            can_resume = all(not child.reconciliation_required for child in recovered_children)
            result[pid] = ParentRecovery(
                parent_id=pid, quantity=parent["quantity"], filled_quantity=filled,
                remaining_size=remaining, children=tuple(recovered_children), can_resume=can_resume,
            )
        return result
