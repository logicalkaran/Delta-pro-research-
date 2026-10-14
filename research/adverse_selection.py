"""Post-fill markout/adverse-selection analytics; no order routing."""
from __future__ import annotations
import math
from typing import Iterable

def _positive(v, name):
    x=float(v)
    if not math.isfinite(x) or x <= 0: raise ValueError(f"{name} must be finite and positive")
    return x

def post_fill_markout(*, side: str, fill_price: float, future_mid: float,
                      future_microprice: float | None = None,
                      observed_volume: float | None = None) -> dict:
    """Signed markout in bps; negative means adverse to the filled side."""
    if side not in {"buy","sell"}: raise ValueError("side must be buy or sell")
    fill=_positive(fill_price,"fill_price"); mid=_positive(future_mid,"future_mid")
    micro=_positive(future_microprice,"future_microprice") if future_microprice is not None else None
    vol=None if observed_volume is None else float(observed_volume)
    if vol is not None and (not math.isfinite(vol) or vol < 0): raise ValueError("observed_volume must be non-negative")
    sign=1.0 if side=="buy" else -1.0
    markout=sign*(mid-fill)/fill*10000.0
    micro_markout=None if micro is None else sign*(micro-fill)/fill*10000.0
    return {"side":side,"fill_price":fill,"future_mid":mid,"future_microprice":micro,
            "markout_bps":markout,"microprice_markout_bps":micro_markout,
            "adverse_selection_bps":max(0.0,-markout),"observed_volume":vol,
            "volume_weight":vol,"status":"OBSERVED_MARKOUT" if vol is not None else "MARKOUT_VOLUME_UNAVAILABLE"}

def volume_weighted_markout(rows: Iterable[dict]) -> dict:
    num=den=0.0; count=0
    for row in rows:
        v=row.get("observed_volume"); x=row.get("markout_bps")
        if v is None or x is None: continue
        v,x=float(v),float(x)
        if not math.isfinite(v) or v < 0 or not math.isfinite(x): raise ValueError("invalid markout row")
        if v == 0: continue
        num += v*x; den += v; count += 1
    return {"volume_weighted_markout_bps": num/den if den else None,
            "total_observed_volume":den,"weighted_observations":count,
            "status":"OK" if den else "INSUFFICIENT_VOLUME"}

def evaluate_expected_value(*, gross_edge_bps: float, maker_rebate_bps: float = 2.0,
                            taker_fee_bps: float = 5.0, other_costs_bps: float = 0.0) -> dict:
    """Conservative explicit fee/rebate gate; rebate is credit, costs are debits.

    Defaults reproduce the supplied specification's assumptions, not verified exchange terms.
    """
    vals=(gross_edge_bps,maker_rebate_bps,taker_fee_bps,other_costs_bps)
    if any(not math.isfinite(float(v)) for v in vals) or maker_rebate_bps < 0 or taker_fee_bps < 0 or other_costs_bps < 0:
        raise ValueError("edge/cost inputs must be finite; fee and cost inputs non-negative")
    net=float(gross_edge_bps)+float(maker_rebate_bps)-float(taker_fee_bps)-float(other_costs_bps)
    return {"gross_edge_bps":float(gross_edge_bps),"maker_rebate_credit_bps":float(maker_rebate_bps),
            "taker_fee_cost_bps":float(taker_fee_bps),"other_costs_bps":float(other_costs_bps),
            "net_expected_value_bps":net,"approved_for_research":net>0,
            "status":"POSITIVE_AFTER_ASSUMED_COSTS" if net>0 else "REJECT_NONPOSITIVE_EXPECTANCY",
            "fee_assumptions_verified":False}
