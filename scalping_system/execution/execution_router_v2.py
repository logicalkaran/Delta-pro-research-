"""V2 execution economics: stricter net-edge gate, dynamic target floor, paper only."""
from dataclasses import dataclass

@dataclass
class ExecutionDecision:
    mode:str; reason:str; expected_edge_bps:float; estimated_cost_bps:float
    queue_cost_bps:float; adverse_selection_bps:float; min_target_bps:float

def decide(*,signal_edge_bps,spread_bps,queue_ahead,recent_delta,recent_return_bps,
           maker_fee_bps=2.36,taker_fee_bps=5.90,tick_bps=0.06):
    queue_cost=min(2.5,max(0.0,queue_ahead/250.0))
    adverse=min(3.0,abs(recent_delta)*3.0+max(0.0,abs(recent_return_bps))*.10)
    maker_cost=maker_fee_bps+spread_bps*.25+queue_cost+adverse
    taker_cost=taker_fee_bps+spread_bps*.50+adverse
    # Minimum gross target needed to have room after a maker entry and taker exit.
    min_target=max(14.0,maker_cost+taker_fee_bps+3.0)
    maker_net=signal_edge_bps-maker_cost
    taker_net=signal_edge_bps-taker_cost
    if signal_edge_bps < min_target:
        return ExecutionDecision("REJECT","EDGE_BELOW_TARGET_FLOOR",signal_edge_bps,min(maker_cost,taker_cost),queue_cost,adverse,min_target)
    if maker_net >= 4.0 and queue_ahead <= 250:
        return ExecutionDecision("MAKER","POSITIVE_NET_EDGE_V2",signal_edge_bps,maker_cost,queue_cost,adverse,min_target)
    if taker_net >= 8.0:
        return ExecutionDecision("TAKER_PAPER","TAKER_NET_EDGE_V2",signal_edge_bps,taker_cost,queue_cost,adverse,min_target)
    return ExecutionDecision("REJECT","INSUFFICIENT_NET_EDGE_V2",signal_edge_bps,min(maker_cost,taker_cost),queue_cost,adverse,min_target)
