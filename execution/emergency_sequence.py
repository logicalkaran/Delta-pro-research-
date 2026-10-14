"""Deterministic emergency policy runner with an injected REST adapter.

Only tests/mocks should be connected until an independently reviewed venue adapter
exists. A request is not considered successful unless the adapter confirms it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Any


class EmergencyAdapter(Protocol):
    def halt_signal_ingestion(self) -> None: ...
    def set_engine_state(self, state: str) -> None: ...
    def cancel_all_open_limit_orders(self) -> dict[str, Any]: ...
    def append_audit_event(self, event: dict[str, Any]) -> None: ...


@dataclass(frozen=True)
class EmergencyResult:
    state: str
    state_persisted: bool
    signal_ingestion_halted: bool
    cancel_requested: bool
    cancel_confirmed: bool
    reasons: tuple[str, ...]
    errors: tuple[str, ...]


def run_emergency_sequence(adapter: EmergencyAdapter, reasons: tuple[str, ...]) -> EmergencyResult:
    errors: list[str] = []
    halted = False
    state_persisted = False
    cancel_requested = False
    cancel_confirmed = False
    state = "EMERGENCY_REDUCE_ONLY"

    # Stop new risk first, then persist the state, then attempt exchange cleanup.
    try:
        adapter.halt_signal_ingestion()
        halted = True
    except Exception as exc:
        errors.append("HALT_SIGNAL_INGESTION_FAILED:" + type(exc).__name__)
    try:
        adapter.set_engine_state(state)
        state_persisted = True
    except Exception as exc:
        errors.append("SET_EMERGENCY_STATE_FAILED:" + type(exc).__name__)
    try:
        cancel_requested = True
        response = adapter.cancel_all_open_limit_orders()
        cancel_confirmed = bool(
            isinstance(response, dict)
            and response.get("success") is True
            and response.get("confirmed") is True
        )
        if not cancel_confirmed:
            errors.append("CANCEL_ALL_NOT_CONFIRMED")
    except Exception as exc:
        errors.append("CANCEL_ALL_REQUEST_FAILED:" + type(exc).__name__)
    event = {
        "event_type": "EMERGENCY_BREAKER_TRIPPED",
        "state": state,
        "state_persisted": state_persisted,
        "reasons": list(reasons),
        "signal_ingestion_halted": halted,
        "cancel_requested": cancel_requested,
        "cancel_confirmed": cancel_confirmed,
        "errors": list(errors),
    }
    try:
        adapter.append_audit_event(event)
    except Exception as exc:
        errors.append("AUDIT_APPEND_FAILED:" + type(exc).__name__)
    return EmergencyResult(state, state_persisted, halted, cancel_requested, cancel_confirmed, reasons, tuple(errors))
