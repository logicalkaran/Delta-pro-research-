"""Pure policy core for the Android/Termux orchestration watchdog.

This evaluates telemetry and emits required actions. It does not call Delta,
cancel orders, or claim an emergency action succeeded; a supervisor must execute
and verify those actions through the authenticated REST client.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math


class WatchdogState(str, Enum):
    NORMAL = "NORMAL"
    DEGRADED = "DEGRADED"
    EMERGENCY_REDUCE_ONLY = "EMERGENCY_REDUCE_ONLY"


@dataclass(frozen=True)
class WatchdogTelemetry:
    websocket_latency_ms: float
    seconds_since_last_heartbeat: float
    market_data_age_seconds: float
    process_memory_mb: float
    heartbeat_received: bool = True
    supervisor_alive: bool = True


@dataclass(frozen=True)
class WatchdogDecision:
    state: WatchdogState
    reasons: tuple[str, ...]
    halt_new_signals: bool
    require_rest_reconciliation: bool
    cancel_open_orders_via_rest: bool
    permit_only_risk_reduction: bool
    manual_reset_required: bool


def evaluate_watchdog(
    telemetry: WatchdogTelemetry,
    *,
    max_latency_ms: float = 500.0,
    max_heartbeat_age_seconds: float = 10.0,
    max_market_age_seconds: float = 2.0,
    max_memory_mb: float = 500.0,
) -> WatchdogDecision:
    """Return a deterministic watchdog decision from one telemetry snapshot."""
    limits = (max_latency_ms, max_heartbeat_age_seconds,
              max_market_age_seconds, max_memory_mb)
    values = (
        telemetry.websocket_latency_ms,
        telemetry.seconds_since_last_heartbeat,
        telemetry.market_data_age_seconds,
        telemetry.process_memory_mb,
    )
    if any(not math.isfinite(x) for x in values + limits):
        reasons = ("NON_FINITE_WATCHDOG_TELEMETRY",)
        return WatchdogDecision(WatchdogState.EMERGENCY_REDUCE_ONLY, reasons, True, True, True, True, True)
    if any(x <= 0 for x in limits):
        raise ValueError("watchdog limits must be positive")
    reasons: list[str] = []
    if not telemetry.supervisor_alive:
        reasons.append("SUPERVISOR_NOT_ALIVE")
    if not telemetry.heartbeat_received:
        reasons.append("WEBSOCKET_HEARTBEAT_MISSING")
    if telemetry.websocket_latency_ms < 0 or telemetry.websocket_latency_ms > max_latency_ms:
        reasons.append("WEBSOCKET_LATENCY_LIMIT")
    if telemetry.seconds_since_last_heartbeat < 0 or telemetry.seconds_since_last_heartbeat > max_heartbeat_age_seconds:
        reasons.append("HEARTBEAT_AGE_LIMIT")
    if telemetry.market_data_age_seconds < 0 or telemetry.market_data_age_seconds > max_market_age_seconds:
        reasons.append("MARKET_DATA_STALE")
    if telemetry.process_memory_mb < 0 or telemetry.process_memory_mb > max_memory_mb:
        reasons.append("MEMORY_LIMIT")

    if not reasons:
        return WatchdogDecision(WatchdogState.NORMAL, (), False, False, False, False, False)

    # Any breached hard threshold trips emergency mode. There is no automatic
    # resume: a human must inspect telemetry and reconcile exchange state.
    return WatchdogDecision(
        state=WatchdogState.EMERGENCY_REDUCE_ONLY,
        reasons=tuple(reasons),
        halt_new_signals=True,
        require_rest_reconciliation=True,
        cancel_open_orders_via_rest=True,
        permit_only_risk_reduction=True,
        manual_reset_required=True,
    )
