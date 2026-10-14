"""Research-only latency gate for measuring market-to-decision readiness.

This is not wired into production execution. Missing, negative or stale latency
measurements fail closed; RTT alone does not prove a market-data feed is fresh.
"""
from __future__ import annotations
from dataclasses import dataclass
from math import isfinite

@dataclass(frozen=True)
class LatencyAssessment:
    eligible_for_paper_evaluation: bool
    reason: str
    round_trip_ms: float | None
    market_age_ms: float | None


def _valid(value):
    try:
        x = float(value)
        return x if isfinite(x) and x >= 0 else None
    except (TypeError, ValueError):
        return None


def assess_latency(round_trip_ms, market_age_ms, max_rtt_ms=50.0, max_market_age_ms=2000.0):
    rtt, age = _valid(round_trip_ms), _valid(market_age_ms)
    if rtt is None or age is None:
        return LatencyAssessment(False, "MISSING_OR_INVALID_LATENCY", rtt, age)
    if max_rtt_ms <= 0 or max_market_age_ms <= 0:
        return LatencyAssessment(False, "INVALID_LIMITS", rtt, age)
    if rtt > max_rtt_ms:
        return LatencyAssessment(False, "ROUND_TRIP_LATENCY_TOO_HIGH", rtt, age)
    if age > max_market_age_ms:
        return LatencyAssessment(False, "MARKET_DATA_STALE", rtt, age)
    return LatencyAssessment(True, "LATENCY_OK_FOR_PAPER_ONLY", rtt, age)
