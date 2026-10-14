"""Thread-safe reservations around the pure risk oracle.

Reservations prevent concurrent entry intents from oversubscribing the local risk
budget. Unknown outcomes stay reserved until private exchange reconciliation.
"""
from __future__ import annotations

from threading import RLock
import math

from risk.orchestration_oracle import (
    OrderIntent, PortfolioSnapshot, RiskLimits, RiskDecision, Verdict, evaluate,
)


class ConcurrentRiskGate:
    def __init__(self, limits: RiskLimits = RiskLimits()):
        self.limits = limits
        self._lock = RLock()
        self._reserved: dict[str, float] = {}

    def reserve(self, intent_id: str, snapshot: PortfolioSnapshot, intent: OrderIntent) -> RiskDecision:
        if not intent_id:
            return RiskDecision(Verdict.REJECTED, 0.0, ("MISSING_INTENT_ID",))
        with self._lock:
            if intent_id in self._reserved:
                return RiskDecision(Verdict.REJECTED, 0.0, ("DUPLICATE_INTENT_ID",))
            if self._reserved:
                # Fail closed rather than netting opposite pending orders whose fills
                # can arrive at different times and create transient gross exposure.
                return RiskDecision(Verdict.REJECTED, 0.0, ("UNRESOLVED_INTENT_RESERVATION",))
            decision = evaluate(snapshot, intent, self.limits)
            if decision.verdict in {Verdict.APPROVED, Verdict.SCALED}:
                self._reserved[intent_id] = decision.approved_signed_quantity_btc
            return decision

    def resolve_cancelled(self, intent_id: str, *, cancellation_confirmed: bool) -> None:
        """Release only after authoritative confirmation that no order can still fill."""
        if cancellation_confirmed is not True:
            raise ValueError("reservation remains until cancellation/rejection is confirmed")
        with self._lock:
            if intent_id not in self._reserved:
                raise KeyError("unknown reservation")
            del self._reserved[intent_id]

    def resolve_filled(self, intent_id: str, *, filled_signed_quantity_btc: float,
                       authoritative_snapshot_updated: bool, order_terminal_confirmed: bool) -> None:
        """Release only after terminal order/fill reconciliation and snapshot refresh."""
        if not math.isfinite(filled_signed_quantity_btc):
            raise ValueError("fill quantity must be finite")
        if authoritative_snapshot_updated is not True or order_terminal_confirmed is not True:
            raise ValueError("terminal order reconciliation and authoritative snapshot update are required")
        with self._lock:
            if intent_id not in self._reserved:
                raise KeyError("unknown reservation")
            reserved = self._reserved[intent_id]
            if (filled_signed_quantity_btc != 0 and reserved * filled_signed_quantity_btc < 0) or abs(filled_signed_quantity_btc) > abs(reserved) + 1e-12:
                raise ValueError("reconciled fill does not match reserved order direction/quantity")
            del self._reserved[intent_id]

    def unresolved_ids(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._reserved))
