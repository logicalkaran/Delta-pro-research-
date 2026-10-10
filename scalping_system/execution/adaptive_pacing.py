"""OFI-aware execution pacing policy; no exchange I/O or order submission."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math


class PaceAction(str, Enum):
    ACCELERATE = "ACCELERATE"
    NORMAL = "NORMAL"
    SLOW = "SLOW"
    WITHDRAW_PASSIVE = "WITHDRAW_PASSIVE"
    HALT_STALE = "HALT_STALE"


@dataclass(frozen=True)
class PaceDecision:
    action: PaceAction
    interval_multiplier: float
    reason: str


def choose_pace(
    *,
    side: str,
    ofi: float,
    microprice_edge_bps: float,
    spread_bps: float,
    market_age_seconds: float,
    passive_order_live: bool,
    max_market_age_seconds: float = 2.0,
    adverse_microprice_bps: float = 0.5,
) -> PaceDecision:
    """Choose child-order cadence from normalized OFI and microprice adversity.

    Positive OFI means bid-side pressure; negative OFI means ask-side pressure.
    microprice_edge_bps is signed in the intended order direction: positive is
    favorable, negative is adverse. Cadence is only a recommendation to the
    execution controller, not a price or size instruction.
    """
    values = (ofi, microprice_edge_bps, spread_bps, market_age_seconds,
              max_market_age_seconds, adverse_microprice_bps)
    if any(not math.isfinite(x) for x in values):
        return PaceDecision(PaceAction.HALT_STALE, 1.0, "NON_FINITE_EXECUTION_TELEMETRY")
    if side not in {"buy", "sell"}:
        raise ValueError("side must be buy or sell")
    if not -1.0 <= ofi <= 1.0 or spread_bps < 0 or market_age_seconds < 0:
        raise ValueError("invalid OFI, spread or market age")
    if max_market_age_seconds <= 0 or adverse_microprice_bps < 0:
        raise ValueError("invalid execution policy limits")
    if market_age_seconds > max_market_age_seconds:
        return PaceDecision(PaceAction.HALT_STALE, 1.0, "MARKET_DATA_STALE")
    if passive_order_live and microprice_edge_bps <= -adverse_microprice_bps:
        return PaceDecision(PaceAction.WITHDRAW_PASSIVE, 1.0, "ADVERSE_MICROPRICE")
    aligned = ofi > 0.15 if side == "buy" else ofi < -0.15
    opposed = ofi < -0.15 if side == "buy" else ofi > 0.15
    if aligned and microprice_edge_bps >= 0:
        return PaceDecision(PaceAction.ACCELERATE, 0.5, "OFI_ALIGNED")
    if opposed or microprice_edge_bps < 0:
        return PaceDecision(PaceAction.SLOW, 2.0, "FLOW_OPPOSED_OR_ADVERSE")
    return PaceDecision(PaceAction.NORMAL, 1.0, "NO_STRONG_EXECUTION_EDGE")
