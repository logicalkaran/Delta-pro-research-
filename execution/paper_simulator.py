"""Local, deterministic paper matching engine. Never submits exchange orders.

Only supplied top-of-book depth and explicit trade prints can cause fills. Maker
rebate and taker fee are configurable assumptions, not a verified Delta fee tier.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import random
import time
from typing import Any, Callable

from execution.adaptive_pacing import choose_pace
from storage.event_journal import EventJournal

D = Decimal


@dataclass
class PaperOrder:
    client_order_id: str
    side: str
    limit_price: Decimal
    quantity: Decimal
    state: str
    ack_due_ms: int
    filled_quantity: Decimal = D("0")
    average_fill_price: Decimal = D("0")

    @property
    def remaining(self) -> Decimal:
        return max(D("0"), self.quantity - self.filled_quantity)


class PaperSimulator:
    TAKER_FEE_RATE = D("0.0005")  # 0.05%; validate against current account tier.
    MAKER_REBATE_RATE = D("0.0002")  # 0.02%; simulation assumption only.

    def __init__(
        self,
        journal: EventJournal,
        *,
        initial_equity: Decimal | str = "10000",
        rng: random.Random | None = None,
        clock_ms: Callable[[], int] | None = None,
        min_latency_ms: int = 100,
        max_latency_ms: int = 400,
        max_book_age_ms: int = 2000,
        taker_fee_rate: Decimal | str = "0.0005",
        maker_rebate_rate: Decimal | str = "0.0002",
    ) -> None:
        if min_latency_ms < 0 or max_latency_ms < min_latency_ms:
            raise ValueError("invalid acknowledgement latency range")
        if max_book_age_ms <= 0:
            raise ValueError("max_book_age_ms must be positive")
        self.journal = journal
        self.rng = rng or random.Random(0)
        self.clock_ms = clock_ms or (lambda: time.time_ns() // 1_000_000)
        self.min_latency_ms, self.max_latency_ms = min_latency_ms, max_latency_ms
        self.max_book_age_ms = max_book_age_ms
        self.taker_fee_rate, self.maker_rebate_rate = D(str(taker_fee_rate)), D(str(maker_rebate_rate))
        if self.taker_fee_rate < 0 or self.maker_rebate_rate < 0:
            raise ValueError("fee and rebate rates must be non-negative")
        self.initial_equity = D(str(initial_equity))
        self.cash = self.initial_equity
        self.position_qty = D("0")
        self.mark_price: Decimal | None = None
        self.book: dict[str, Any] | None = None
        self.orders: dict[str, PaperOrder] = {}
        self._event_counter = 0
        self._last_now_ms = 0
        self._restore_from_journal()

    def _restore_from_journal(self) -> None:
        integrity = self.journal.verify()
        if not integrity.get("valid"):
            raise RuntimeError("paper simulator journal integrity failure")
        events = self.journal.replay()
        self._event_counter = int(integrity.get("last_seq", 0))
        for event in events:
            kind, payload = event["event_type"], event["payload"]
            cid = payload.get("client_order_id")
            if kind == "CHILD_DISPATCHED" and str(event.get("event_id", "")).startswith("paper:") and cid:
                self.orders[str(cid)] = PaperOrder(
                    str(cid), str(payload["side"]), D(str(payload["limit_price"])),
                    D(str(payload["quantity"])), "DISPATCHED", int(payload["ack_due_ms"]),
                )
            elif cid and str(cid) in self.orders:
                order = self.orders[str(cid)]
                if kind == "CHILD_ACKNOWLEDGED":
                    order.state = "ACKNOWLEDGED"
                elif kind == "CHILD_ACK_DEFERRED_STALE_BOOK":
                    order.state = "UNKNOWN"
                elif kind in {"CHILD_PARTIAL_FILL", "CHILD_FILLED"}:
                    qty = D(str(payload.get("fill_quantity", "0")))
                    price = D(str(payload.get("fill_price", "0")))
                    old_qty = order.filled_quantity
                    new_qty = old_qty + qty
                    if new_qty > 0:
                        order.average_fill_price = (order.average_fill_price * old_qty + price * qty) / new_qty
                    order.filled_quantity = new_qty
                    order.state = "FILLED" if kind == "CHILD_FILLED" else "PARTIAL_FILL"
                    notional = qty * price
                    self.cash += -notional if payload.get("side") == "buy" else notional
                    self.position_qty += qty if payload.get("side") == "buy" else -qty
                elif kind in {"PAPER_FEE", "PAPER_REBATE"}:
                    self.cash += D(str(payload.get("equity_delta", "0")))
        for order in self.orders.values():
            if order.state == "ACKNOWLEDGED":
                order.state = "RESTING"

    def _emit(self, event_type: str, client_order_id: str, now_ms: int, **payload: Any) -> dict[str, Any]:
        self._event_counter += 1
        return self.journal.append(
            f"paper:{client_order_id}:{self._event_counter:06d}",
            event_type,
            {"client_order_id": client_order_id, "now_ms": int(now_ms), **payload},
            ts_ns=int(now_ms) * 1_000_000,
        )

    @staticmethod
    def _positive(value: Any, name: str, *, allow_zero: bool = False) -> Decimal:
        try:
            out = D(str(value))
        except (InvalidOperation, ValueError, TypeError):
            raise ValueError(f"invalid {name}") from None
        if not out.is_finite() or (out < 0 if allow_zero else out <= 0):
            raise ValueError(f"invalid {name}")
        return out

    def update_book(
        self, *, bid: Any, ask: Any, mark: Any, bid_size: Any, ask_size: Any, timestamp_ms: int
    ) -> None:
        b = self._positive(bid, "bid")
        a = self._positive(ask, "ask")
        m = self._positive(mark, "mark")
        bs = self._positive(bid_size, "bid_size", allow_zero=True)
        ass = self._positive(ask_size, "ask_size", allow_zero=True)
        if b >= a:
            raise ValueError("crossed or locked book; refusing simulation")
        if timestamp_ms < 0 or timestamp_ms > int(self.clock_ms()) + self.max_book_age_ms:
            raise ValueError("invalid/future book timestamp")
        self.book = {"bid": b, "ask": a, "bid_size": bs, "ask_size": ass, "timestamp_ms": int(timestamp_ms)}
        self.mark_price = m

    def _require_fresh_book(self, now_ms: int) -> dict[str, Any]:
        if self.book is None or self.mark_price is None:
            raise RuntimeError("book unavailable")
        age = now_ms - self.book["timestamp_ms"]
        if age < 0 or age > self.max_book_age_ms:
            raise RuntimeError("stale market book; fail-closed")
        return self.book

    def recommend_pace(self, *, side: str, ofi: float, microprice_edge_bps: float, spread_bps: float,
                       market_age_seconds: float, passive_order_live: bool):
        """Pacing recommendation only; never alters signal or order side/size."""
        return choose_pace(
            side=side, ofi=ofi, microprice_edge_bps=microprice_edge_bps,
            spread_bps=spread_bps, market_age_seconds=market_age_seconds,
            passive_order_live=passive_order_live,
        )

    def create_parent(self, parent_id: str, quantity: Any, *, now_ms: int) -> dict[str, Any]:
        if not parent_id:
            raise ValueError("parent_id required")
        q = self._positive(quantity, "parent quantity")
        event_id = f"paper-parent:{parent_id}"
        for event in self.journal.replay():
            if event["event_id"] == event_id:
                payload = event["payload"]
                if D(str(payload.get("quantity"))) != q:
                    raise ValueError("parent_id reused with different quantity")
                return event
        return self.journal.append(
            event_id, "PARENT_CREATED",
            {"parent_id": parent_id, "quantity": str(q), "now_ms": int(now_ms)},
            ts_ns=int(now_ms) * 1_000_000,
        )

    def submit_limit(self, *, client_order_id: str, parent_id: str, side: str,
                     limit_price: Any, quantity: Any, now_ms: int) -> PaperOrder:
        if not client_order_id or not parent_id:
            raise ValueError("stable client_order_id and parent_id required")
        if side not in {"buy", "sell"}:
            raise ValueError("side must be buy or sell")
        price, qty = self._positive(limit_price, "limit price"), self._positive(quantity, "quantity")
        existing = self.orders.get(client_order_id)
        if existing:
            if (existing.side, existing.limit_price, existing.quantity) != (side, price, qty):
                raise ValueError("client_order_id reused with different order parameters")
            return existing
        book = self._require_fresh_book(now_ms)
        latency = self.rng.randint(self.min_latency_ms, self.max_latency_ms)
        order = PaperOrder(client_order_id, side, price, qty, "DISPATCHED", now_ms + latency)
        self.orders[client_order_id] = order
        self._emit("CHILD_DISPATCHED", client_order_id, now_ms, parent_id=parent_id,
                   side=side, limit_price=str(price), quantity=str(qty), ack_due_ms=order.ack_due_ms)
        return order

    def advance(self, *, now_ms: int) -> list[dict[str, Any]]:
        if now_ms < self._last_now_ms:
            raise ValueError("simulation clock cannot move backwards")
        emitted = []
        for order in sorted(self.orders.values(), key=lambda o: (o.ack_due_ms, o.client_order_id)):
            if order.state != "DISPATCHED" or order.ack_due_ms > now_ms:
                continue
            try:
                book = self._require_fresh_book(order.ack_due_ms)
            except RuntimeError:
                order.state = "UNKNOWN"
                emitted.append(self._emit("CHILD_ACK_DEFERRED_STALE_BOOK", order.client_order_id,
                                          order.ack_due_ms, state=order.state))
                continue
            order.state = "ACKNOWLEDGED"
            emitted.append(self._emit("CHILD_ACKNOWLEDGED", order.client_order_id, order.ack_due_ms,
                                      parent_id=self._parent_id(order.client_order_id)))
            marketable = (order.side == "buy" and order.limit_price >= book["ask"]) or (
                order.side == "sell" and order.limit_price <= book["bid"])
            if marketable:
                available = book["ask_size"] if order.side == "buy" else book["bid_size"]
                fill_qty = min(order.remaining, available)
                if fill_qty > 0:
                    fill_price = book["ask"] if order.side == "buy" else book["bid"]
                    emitted.extend(self._fill(order, fill_qty, fill_price, "TAKER", order.ack_due_ms))
                    if order.remaining > 0:
                        order.state = "PARTIAL_FILL"
            if order.state == "ACKNOWLEDGED":
                order.state = "RESTING"
        self._last_now_ms = now_ms
        return emitted

    def _parent_id(self, client_order_id: str) -> str:
        for event in reversed(self.journal.replay()):
            payload = event.get("payload", {})
            if payload.get("client_order_id") == client_order_id and payload.get("parent_id"):
                return str(payload["parent_id"])
        return "unknown"

    def on_trade(self, *, price: Any, quantity: Any, aggressor_side: str, now_ms: int) -> list[dict[str, Any]]:
        p = self._positive(price, "trade price")
        q = self._positive(quantity, "trade quantity")
        if aggressor_side not in {"buy", "sell"}:
            raise ValueError("aggressor_side must be buy or sell")
        self._require_fresh_book(now_ms)
        out = []
        for order in sorted(self.orders.values(), key=lambda o: o.client_order_id):
            if order.state not in {"RESTING", "PARTIAL_FILL"}:
                continue
            crosses = p <= order.limit_price if order.side == "buy" else p >= order.limit_price
            opposite_aggressor = aggressor_side != order.side
            if crosses and opposite_aggressor:
                fill_qty = min(order.remaining, q)
                if fill_qty > 0:
                    out.extend(self._fill(order, fill_qty, order.limit_price, "MAKER", now_ms))
                    q -= fill_qty
                    if q <= 0:
                        break
        return out

    def _fill(self, order: PaperOrder, quantity: Decimal, price: Decimal, route: str, now_ms: int):
        old_qty = order.filled_quantity
        total = old_qty + quantity
        order.average_fill_price = ((order.average_fill_price * old_qty) + price * quantity) / total
        order.filled_quantity = total
        notional = quantity * price
        if order.side == "buy":
            self.cash -= notional
            self.position_qty += quantity
        else:
            self.cash += notional
            self.position_qty -= quantity
        rate = self.taker_fee_rate if route == "TAKER" else -self.maker_rebate_rate
        fee = notional * rate
        self.cash -= fee
        order.state = "FILLED" if order.remaining == 0 else "PARTIAL_FILL"
        fill_type = "CHILD_FILLED" if order.state == "FILLED" else "CHILD_PARTIAL_FILL"
        rows = [self._emit(fill_type, order.client_order_id, now_ms, parent_id=self._parent_id(order.client_order_id),
                           side=order.side, route=route, fill_quantity=str(quantity), fill_price=str(price),
                           cumulative_filled=str(order.filled_quantity), remaining_quantity=str(order.remaining),
                           notional=str(notional))]
        rows.append(self._emit("PAPER_FEE" if fee >= 0 else "PAPER_REBATE", order.client_order_id, now_ms,
                               amount=str(abs(fee)), equity_delta=str(-fee), route=route))
        return rows

    def snapshot(self) -> dict[str, str | None]:
        unrealized = (self.position_qty * self.mark_price) if self.mark_price is not None else D("0")
        return {"cash": str(self.cash), "position_qty": str(self.position_qty),
                "mark_price": str(self.mark_price) if self.mark_price is not None else None,
                "equity": str(self.cash + unrealized)}
