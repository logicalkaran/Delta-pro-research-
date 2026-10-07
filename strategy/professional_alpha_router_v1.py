"""Professional Alpha Router V1.
Combines independent research layers without changing production execution.
"""
from dataclasses import dataclass

@dataclass(frozen=True)
class RouterConfig:
    max_spread_bps: float=5.0
    max_stale_s: float=2.0
    min_score: int=8
    require_cross_venue_validation: bool=True

def route(*,base_action,score,data_age_s,spread_bps,session_ok,cross_validated,
          risk_ok=True,news_block=False):
    reasons=[]
    if data_age_s>2: reasons.append("STALE_DATA")
    if spread_bps>5: reasons.append("SPREAD_STRESS")
    if not session_ok: reasons.append("SESSION_BLOCK")
    if news_block: reasons.append("NEWS_BLOCK")
    if not risk_ok: reasons.append("RISK_BLOCK")
    if cross_validated is False: reasons.append("CROSS_VENUE_UNVALIDATED")
    if score<8: reasons.append("EDGE_SCORE_LOW")
    if reasons: return {"action":"NO_TRADE","reasons":reasons,"base_action":base_action,"score":score}
    if base_action not in ("LONG","SHORT"): return {"action":"NO_TRADE","reasons":["NO_DIRECTION"]}
    return {"action":base_action,"reasons":["ALL_GATES_PASS"],"score":score}

def paper_only_check(route_result):
    return {**route_result,"execution":"PAPER_ONLY","order_submission":False}
