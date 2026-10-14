"""Crash-recoverable TWAP parent/child ledger for PAPER/SHADOW use only.

This module contains no exchange client and cannot submit live orders. It creates
stable client IDs and persists intent before a child can be dispatched. On restart,
unknown acknowledgements require reconciliation; they are never blindly resent.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Iterable

TERMINAL = {"FILLED", "CANCELED", "REJECTED"}


@dataclass(frozen=True)
class ChildOrder:
    client_order_id: str
    parent_id: str
    ordinal: int
    quantity: float
    filled_quantity: float
    due_ms: int
    state: str
    exchange_order_id: str | None


@dataclass(frozen=True)
class ChaseDecision:
    action: str
    target_price: float | None
    chase_ticks: int
    reason: str


def evaluate_chase(*, side: str, passive_price: float, best_bid: float, best_ask: float,
                   tick_size: float, max_chase_ticks: int = 3) -> ChaseDecision:
    """Never cross the spread. Reprice only within the configured tick distance."""
    import math
    vals = (passive_price, best_bid, best_ask, tick_size)
    if any(not math.isfinite(v) for v in vals) or min(passive_price, best_bid, best_ask, tick_size) <= 0:
        return ChaseDecision("REJECT", None, 0, "INVALID_PRICE_TELEMETRY")
    if side not in {"buy", "sell"} or max_chase_ticks < 0:
        return ChaseDecision("REJECT", None, 0, "INVALID_CHASE_POLICY")
    if best_bid >= best_ask:
        return ChaseDecision("WAIT_NEXT_INTERVAL", None, 0, "CROSSED_OR_LOCKED_BOOK")
    desired = best_bid if side == "buy" else best_ask
    # A buy must stay below ask; a sell must stay above bid.
    ratios = (passive_price / tick_size, best_bid / tick_size, best_ask / tick_size)
    if any(abs(ratio - round(ratio)) > 1e-8 for ratio in ratios):
        return ChaseDecision("REJECT", None, 0, "PRICE_OFF_TICK_GRID")
    ticks = int(math.ceil(abs(desired - passive_price) / tick_size - 1e-12))
    if ticks > max_chase_ticks:
        return ChaseDecision("WAIT_NEXT_INTERVAL", None, ticks, "CHASE_LIMIT_BREACHED")
    if side == "buy":
        target = min(desired, best_ask - tick_size)
    else:
        target = max(desired, best_bid + tick_size)
    if target <= 0 or (side == "buy" and target >= best_ask) or (side == "sell" and target <= best_bid):
        return ChaseDecision("WAIT_NEXT_INTERVAL", None, ticks, "PASSIVE_PRICE_UNAVAILABLE")
    return ChaseDecision("REPRICE_PASSIVE", target, ticks, "WITHIN_CHASE_LIMIT")


class TwapLedger:
    def __init__(self, path: str | Path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, timeout=5.0)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("PRAGMA busy_timeout=5000")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS parents(
          parent_id TEXT PRIMARY KEY, total_qty REAL NOT NULL, child_count INTEGER NOT NULL,
          start_ms INTEGER NOT NULL, duration_ms INTEGER NOT NULL, state TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS children(
          client_order_id TEXT PRIMARY KEY, parent_id TEXT NOT NULL,
          ordinal INTEGER NOT NULL, quantity REAL NOT NULL, filled_quantity REAL NOT NULL DEFAULT 0,
          due_ms INTEGER NOT NULL, state TEXT NOT NULL, exchange_order_id TEXT,
          UNIQUE(parent_id, ordinal),
          FOREIGN KEY(parent_id) REFERENCES parents(parent_id)
        );
        CREATE INDEX IF NOT EXISTS children_due_idx ON children(state, due_ms);
        """)
        columns = {row["name"] for row in self.db.execute("PRAGMA table_info(children)")}
        if "filled_quantity" not in columns:
            self.db.execute("ALTER TABLE children ADD COLUMN filled_quantity REAL NOT NULL DEFAULT 0")
        self.db.commit()

    def create_parent(self, parent_id: str, total_qty: float, *, child_count: int = 10,
                      start_ms: int, duration_ms: int = 7_200_000) -> list[ChildOrder]:
        import math
        if not parent_id or not math.isfinite(total_qty) or total_qty <= 0:
            raise ValueError("parent ID and positive finite quantity required")
        if child_count < 1 or duration_ms <= 0 or start_ms < 0:
            raise ValueError("invalid TWAP schedule")
        with self.db:
            existing = self.db.execute("SELECT * FROM parents WHERE parent_id=?", (parent_id,)).fetchone()
            if existing:
                signature = (existing["total_qty"], existing["child_count"], existing["start_ms"], existing["duration_ms"])
                if signature != (total_qty, child_count, start_ms, duration_ms):
                    raise ValueError("parent ID already exists with different parameters")
                return self.children(parent_id)
            self.db.execute("INSERT INTO parents VALUES(?,?,?,?,?,?)",
                            (parent_id, total_qty, child_count, start_ms, duration_ms, "ACTIVE"))
            base_qty = total_qty / child_count
            for ordinal in range(1, child_count + 1):
                qty = total_qty - base_qty * (child_count - 1) if ordinal == child_count else base_qty
                due = start_ms + (ordinal - 1) * (duration_ms // child_count)
                client_id = f"{parent_id}:{ordinal:04d}"
                self.db.execute(
                    "INSERT INTO children(client_order_id,parent_id,ordinal,quantity,filled_quantity,due_ms,state,exchange_order_id) "
                    "VALUES(?,?,?,?,?,?,?,NULL)",
                    (client_id, parent_id, ordinal, qty, 0.0, due, "PENDING"),
                )
        return self.children(parent_id)

    def children(self, parent_id: str) -> list[ChildOrder]:
        rows = self.db.execute("SELECT * FROM children WHERE parent_id=? ORDER BY ordinal", (parent_id,)).fetchall()
        return [ChildOrder(r["client_order_id"], r["parent_id"], r["ordinal"], r["quantity"],
                           r["filled_quantity"], r["due_ms"], r["state"], r["exchange_order_id"]) for r in rows]

    def due_child(self, parent_id: str, now_ms: int) -> ChildOrder | None:
        # Do not catch up by releasing a burst of overdue children after Android
        # suspension. Resolve/reconcile the previous child before another is eligible.
        active = self.db.execute(
            "SELECT 1 FROM children WHERE parent_id=? AND state IN ('SUBMITTING','SUBMITTED','UNKNOWN') LIMIT 1",
            (parent_id,),
        ).fetchone()
        if active:
            return None
        row = self.db.execute(
            "SELECT * FROM children WHERE parent_id=? AND state='PENDING' AND due_ms<=? ORDER BY ordinal LIMIT 1",
            (parent_id, now_ms)).fetchone()
        return self._child(row) if row else None

    @staticmethod
    def _child(r) -> ChildOrder:
        return ChildOrder(r["client_order_id"], r["parent_id"], r["ordinal"], r["quantity"],
                          r["filled_quantity"], r["due_ms"], r["state"], r["exchange_order_id"])

    def mark_submitting(self, client_order_id: str) -> ChildOrder:
        """Durably reserve dispatch before network I/O; only PENDING can transition."""
        with self.db:
            cur = self.db.execute("UPDATE children SET state='SUBMITTING' WHERE client_order_id=? AND state='PENDING'",
                                  (client_order_id,))
            if cur.rowcount != 1:
                raise ValueError("child is not pending; refusing duplicate dispatch")
        row = self.db.execute("SELECT * FROM children WHERE client_order_id=?", (client_order_id,)).fetchone()
        return self._child(row)

    def record_ack(self, client_order_id: str, exchange_order_id: str) -> None:
        if not exchange_order_id:
            raise ValueError("exchange order ID required")
        with self.db:
            cur = self.db.execute("UPDATE children SET state='SUBMITTED', exchange_order_id=? "
                                  "WHERE client_order_id=? AND state='SUBMITTING'",
                                  (exchange_order_id, client_order_id))
            if cur.rowcount != 1:
                raise ValueError("child is not awaiting acknowledgement")

    def record_result(self, client_order_id: str, *, state: str, filled_quantity: float,
                      exchange_order_id: str | None = None) -> None:
        """Persist authoritative private-order-history result before next child dispatch."""
        import math
        if state not in TERMINAL:
            raise ValueError("state must be FILLED, CANCELED, or REJECTED")
        if not math.isfinite(filled_quantity) or filled_quantity < 0:
            raise ValueError("filled_quantity must be finite and non-negative")
        row = self.db.execute("SELECT * FROM children WHERE client_order_id=?", (client_order_id,)).fetchone()
        if row is None:
            raise KeyError("unknown child order")
        if filled_quantity > row["quantity"] + 1e-12:
            raise ValueError("filled quantity exceeds child quantity")
        if state == "FILLED" and abs(filled_quantity - row["quantity"]) > 1e-12:
            raise ValueError("FILLED state requires full child quantity")
        if row["state"] not in {"SUBMITTING", "SUBMITTED", "UNKNOWN"}:
            raise ValueError("child is not awaiting an authoritative result")
        with self.db:
            self.db.execute(
                "UPDATE children SET state=?, filled_quantity=?, exchange_order_id=COALESCE(?,exchange_order_id) "
                "WHERE client_order_id=?",
                (state, filled_quantity, exchange_order_id, client_order_id),
            )

    def refresh_parent_state(self, parent_id: str) -> dict[str, float | int | str]:
        """Derive parent progress from persisted child results; never infer fills from absence."""
        with self.db:
            parent = self.db.execute("SELECT * FROM parents WHERE parent_id=?", (parent_id,)).fetchone()
            if parent is None:
                raise KeyError("unknown parent order")
            rows = self.db.execute("SELECT state, quantity, filled_quantity FROM children WHERE parent_id=?", (parent_id,)).fetchall()
            filled = sum(float(r["filled_quantity"]) for r in rows)
            terminal = all(r["state"] in TERMINAL for r in rows)
            state = ("COMPLETE" if filled >= float(parent["total_qty"]) - 1e-12 else "INCOMPLETE") if terminal else "ACTIVE"
            self.db.execute("UPDATE parents SET state=? WHERE parent_id=?", (state, parent_id))
        return {"parent_id": parent_id, "state": state, "total_quantity": float(parent["total_qty"]),
                "filled_quantity": filled, "remaining_quantity": max(0.0, float(parent["total_qty"]) - filled),
                "child_count": len(rows), "terminal_children": sum(r["state"] in TERMINAL for r in rows)}

    def reconcile(self, parent_id: str, exchange_open_client_ids: Iterable[str]) -> dict[str, list[str]]:
        """Match open orders and mark absent in-flight orders UNKNOWN; never blindly resend."""
        open_ids = set(exchange_open_client_ids)
        matched, unknown = [], []
        with self.db:
            rows = self.db.execute("SELECT * FROM children WHERE parent_id=?", (parent_id,)).fetchall()
            for row in rows:
                cid = row["client_order_id"]
                if cid in open_ids:
                    matched.append(cid)
                    if row["state"] == "SUBMITTING":
                        self.db.execute("UPDATE children SET state='SUBMITTED' WHERE client_order_id=?", (cid,))
                elif row["state"] in {"SUBMITTING", "SUBMITTED"}:
                    # Absence from open orders does not prove failure: it may have filled,
                    # been canceled, or been rejected. Require private fill/order-history lookup.
                    self.db.execute("UPDATE children SET state='UNKNOWN' WHERE client_order_id=?", (cid,))
                    unknown.append(cid)
        return {"matched_open": matched, "needs_fill_history_reconciliation": unknown}

    def close(self) -> None:
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
