"""Professional microstructure upgrade: OFI proxies, liquidity stress and adverse-selection estimates.

Research-only. No exchange/order submission.
"""
from dataclasses import dataclass

@dataclass(frozen=True)
class ProConfig:
    max_spread_bps: float = 5.0
    min_depth: float = 1000.0
    max_adverse: float = 0.65

def _f(x,d=0.0):
    try: return float(x)
    except (TypeError,ValueError): return d

def professional_features(f):
    spread=_f(f.get("spread_bps"))
    bid=_f(f.get("bid_depth_5"))
    ask=_f(f.get("ask_depth_5"))
    total=max(bid+ask,1e-9)
    depth_ratio=min(1.0,total/100000.0)
    # Proxy OFI: trade pressure plus displayed depth skew.
    ofi_proxy=0.60*_f(f.get("aggression_pressure"))+0.40*_f(f.get("depth_skew"))
    # Higher spread and thinner depth imply worse execution conditions.
    spread_stress=min(1.0,spread/5.0)
    depth_stress=1.0-depth_ratio
    liquidity_stress=0.55*spread_stress+0.45*depth_stress
    # Adverse-selection proxy rises when momentum and flow disagree with the book.
    directional_flow=_f(f.get("delta5"))+_f(f.get("delta30"))
    book=_f(f.get("book_imbalance"))
    divergence=min(1.0,abs(directional_flow)*0.8+max(0.0,-directional_flow*book)*2.0)
    adverse=min(1.0,0.55*liquidity_stress+0.45*divergence)
    return {**f,"ofi_proxy":ofi_proxy,"liquidity_stress":liquidity_stress,"adverse_selection":adverse}

def professional_decision(f,cfg=ProConfig()):
    pf=professional_features(f)
    if pf["spread_bps"]>cfg.max_spread_bps:
        return {"action":"NO_TRADE","reason":"SPREAD_STRESS",**pf}
    if pf.get("liquidity_stress",1)>0.80:
        return {"action":"NO_TRADE","reason":"LIQUIDITY_STRESS",**pf}
    if pf["adverse_selection"]>cfg.max_adverse:
        return {"action":"NO_TRADE","reason":"ADVERSE_SELECTION",**pf}
    base_long=(2*max(0,_f(pf.get("delta5")))+1.5*max(0,_f(pf.get("delta30")))+1.5*max(0,_f(pf.get("book_imbalance")))+1.0*max(0,_f(pf.get("momentum_5"))))
    base_short=(2*max(0,-_f(pf.get("delta5")))+1.5*max(0,-_f(pf.get("delta30")))+1.5*max(0,-_f(pf.get("book_imbalance")))+1.0*max(0,-_f(pf.get("momentum_5"))))
    penalty=pf["liquidity_stress"]+pf["adverse_selection"]
    long_score=base_long-penalty
    short_score=base_short-penalty
    if max(long_score,short_score)<0.25:
        return {"action":"NO_TRADE","reason":"INSUFFICIENT_NET_EDGE","long_score":long_score,"short_score":short_score,**pf}
    action="LONG" if long_score>short_score else "SHORT"
    return {"action":action,"score":max(long_score,short_score),"reason":"NET_EDGE_AFTER_EXECUTION_STRESS",**pf}
