"""Unified research-only probabilistic scalper core.

Combines existing microstructure/flow/context evidence into calibrated action
probabilities and an after-cost expected-value decision. It does not submit
orders, change risk/leverage, or mutate production execution policy.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from math import exp
from typing import Mapping

@dataclass(frozen=True)
class CostModel:
    maker_bps: float = 2.36
    taker_bps: float = 5.90
    spread_bps: float = 0.0
    slippage_bps: float = 1.0
    adverse_selection_bps: float = 1.5

    @property
    def round_trip_bps(self):
        return 2.0*(self.taker_bps + self.spread_bps + self.slippage_bps + self.adverse_selection_bps)

@dataclass(frozen=True)
class Forecast:
    p_up: float
    p_down: float
    p_flat: float
    uncertainty: float
    expected_move_bps: float

@dataclass(frozen=True)
class Decision:
    action: str
    confidence: float
    expected_net_bps: float
    forecast: Forecast
    reasons: tuple[str,...]

class UnifiedProbabilisticScalper:
    """Small deterministic ensemble; learned weights must be supplied by research."""
    def __init__(self, weights: Mapping[str,float]|None=None, cost: CostModel|None=None):
        self.weights=dict(weights or {
            'imbalance':0.25,'flow':0.25,'momentum':0.15,'structure':0.15,
            'regime':0.10,'liquidity':0.10})
        self.cost=cost or CostModel()

    @staticmethod
    def _clip(x): return max(-1.0,min(1.0,float(x)))

    def forecast(self, state: Mapping[str,float]) -> Forecast:
        score=0.0; used=0.0
        aliases={'imbalance':'imbalance','flow':'flow','momentum':'momentum','structure':'structure','regime':'regime','liquidity':'liquidity'}
        for name,w in self.weights.items():
            if name in state:
                score += w*self._clip(state[name]); used += abs(w)
        score = score/used if used else 0.0
        # Conservative mapping: reserve probability mass for uncertainty/flat moves.
        strength=1.0/(1.0+exp(-3.0*score))
        edge=abs(score)*20.0
        uncertainty=max(0.0,1.0-min(1.0,abs(score)*1.5))
        p_up=0.5 + (strength-0.5)*0.75
        p_down=1.0-p_up
        p_flat=min(0.45,uncertainty*0.35)
        scale=1.0-p_flat
        p_up*=scale; p_down*=scale
        return Forecast(round(p_up,6),round(p_down,6),round(p_flat,6),round(uncertainty,6),round((p_up-p_down)*edge,6))

    def decide(self,state:Mapping[str,float],target_bps:float=20.0,min_net_bps:float=1.0)->Decision:
        f=self.forecast(state); cost=self.cost.round_trip_bps
        long_net=f.p_up*target_bps-f.p_down*(target_bps*0.5)-cost
        short_net=f.p_down*target_bps-f.p_up*(target_bps*0.5)-cost
        best=max(long_net,short_net)
        action='LONG' if long_net>short_net else 'SHORT'
        confidence=max(f.p_up,f.p_down)
        reasons=[]
        if f.uncertainty>0.65: reasons.append('HIGH_MODEL_UNCERTAINTY')
        if best<min_net_bps: reasons.append('AFTER_COST_EDGE_INSUFFICIENT')
        if action=='LONG' and f.p_up<=f.p_down: reasons.append('NO_DIRECTIONAL_ADVANTAGE')
        if action=='SHORT' and f.p_down<=f.p_up: reasons.append('NO_DIRECTIONAL_ADVANTAGE')
        if reasons: action='ABSTAIN'
        return Decision(action,round(confidence,6),round(best,6),f,tuple(reasons))

if __name__=='__main__':
    print(asdict(UnifiedProbabilisticScalper().decide({'imbalance':0.4,'flow':0.5,'momentum':0.2,'structure':0.3,'regime':0.2,'liquidity':0.1})))
