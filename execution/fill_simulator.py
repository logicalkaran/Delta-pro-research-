"""Conservative fill/cost simulator for BTC scalping research and paper mode."""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class FillModel:
    maker_fee_bps: float = 2.36
    taker_fee_bps: float = 5.90
    spread_bps: float = 2.0
    slippage_bps: float = 1.0
    adverse_selection_bps: float = 1.0
    maker_fill_probability: float = 0.35

@dataclass(frozen=True)
class FillResult:
    filled: bool
    entry_cost_bps: float
    exit_cost_bps: float
    total_cost_bps: float
    net_edge_bps: float
    route: str

def simulate(signal_edge_bps: float, route: str, model: FillModel = FillModel(),
             queue_ahead: float = 0.0, rng_value: float = 0.0) -> FillResult:
    route = route.upper()
    if route not in {"MAKER", "TAKER"}:
        raise ValueError("route must be MAKER or TAKER")
    if not 0.0 <= rng_value <= 1.0:
        raise ValueError("rng_value must be in [0,1]")
    if route == "MAKER":
        filled = rng_value <= model.maker_fill_probability and queue_ahead <= 250
        entry = model.maker_fee_bps + model.spread_bps * 0.25 + model.adverse_selection_bps
        exit_cost = model.taker_fee_bps + model.spread_bps * 0.50
    else:
        filled = True
        entry = model.taker_fee_bps + model.spread_bps * 0.50 + model.slippage_bps
        exit_cost = model.taker_fee_bps + model.spread_bps * 0.50 + model.slippage_bps
    total = entry + exit_cost
    return FillResult(filled, entry, exit_cost, total,
                      signal_edge_bps - total if filled else 0.0, route)
