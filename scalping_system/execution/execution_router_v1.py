"""Execution-aware paper decision layer. No exchange order submission."""
from dataclasses import dataclass

@dataclass
class ExecutionDecision:
    mode: str
    reason: str
    expected_edge_bps: float
    estimated_cost_bps: float
    queue_cost_bps: float
    adverse_selection_bps: float

def decide(*, signal_edge_bps, spread_bps, queue_ahead, recent_delta, recent_return_bps,
           maker_fee_bps=2.36, taker_fee_bps=5.90, tick_bps=0.06):
    # Conservative estimates; these are for paper routing, not guaranteed fills.
    queue_cost = min(2.5, max(0.0, queue_ahead / 250.0))
    adverse = min(3.0, abs(recent_delta) * 3.0 + max(0.0, abs(recent_return_bps)) * .10)
    maker_cost = maker_fee_bps + spread_bps * .25 + queue_cost + adverse
    taker_cost = taker_fee_bps + spread_bps * .50 + adverse
    maker_net = signal_edge_bps - maker_cost
    taker_net = signal_edge_bps - taker_cost

    if signal_edge_bps <= 0:
        return ExecutionDecision("REJECT","NO_POSITIVE_EDGE",signal_edge_bps,maker_cost,queue_cost,adverse)
    if maker_net >= .50 and queue_ahead <= 300:
        return ExecutionDecision("MAKER","POSITIVE_NET_EDGE",signal_edge_bps,maker_cost,queue_cost,adverse)
    if taker_net >= .50:
        return ExecutionDecision("TAKER_PAPER","MAKER_NOT_EFFICIENT",signal_edge_bps,taker_cost,queue_cost,adverse)
    return ExecutionDecision("REJECT","EXECUTION_COST_EXCEEDS_EDGE",signal_edge_bps,min(maker_cost,taker_cost),queue_cost,adverse)
