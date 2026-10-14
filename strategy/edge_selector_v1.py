"""High-selectivity edge gate for BTC scalping.

This module does not submit orders. It ranks an already-generated signal and
only accepts unusually strong confluence. It is intentionally conservative
about execution costs and account preservation.
"""
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class EdgeConfig:
    min_score: float = 80.0
    min_confidence: float = 0.70
    min_rr: float = 2.50
    max_spread_bps: float = 3.0
    max_fresh_seconds: float = 1.5
    max_oi_rise_pct: float = 0.02
    max_daily_loss_fraction: float = 0.15
    max_consecutive_losses: int = 2

@dataclass(frozen=True)
class EdgeDecision:
    allowed: bool
    score: float
    reasons: tuple[str, ...]
    action: str

def _f(x: Any, d=0.0):
    try: return float(x)
    except (TypeError,ValueError): return d

def score_signal(signal, micro: dict, oi_change_pct: float,
                 cfg: EdgeConfig = EdgeConfig(),
                 daily_loss_fraction: float = 0.0,
                 consecutive_losses: int = 0) -> EdgeDecision:
    if not getattr(signal, "valid", False):
        return EdgeDecision(False, 0.0, ("BASE_SIGNAL_INVALID",), "NO_TRADE")

    price=_f(micro.get("order_book",{}).get("mid_price"))
    spread=_f(micro.get("order_book",{}).get("spread"), 999)
    fresh=_f(micro.get("quality",{}).get("fresh_seconds"),999)
    spread_bps=spread/price*10000 if price>0 else 999
    rr=_f(getattr(signal,"rr",0))
    confidence=_f(getattr(signal,"confidence",0))
    score=0.0
    reasons=[]

    if confidence>=0.85: score+=20; reasons.append("CONFIDENCE_HIGH")
    elif confidence>=cfg.min_confidence: score+=12; reasons.append("CONFIDENCE_ACCEPTED")
    else: reasons.append("CONFIDENCE_LOW")

    if rr>=3.0: score+=20; reasons.append("RR_3_PLUS")
    elif rr>=cfg.min_rr: score+=15; reasons.append("RR_2_5_PLUS")
    else: reasons.append("RR_TOO_LOW")

    if spread_bps<=cfg.max_spread_bps: score+=10; reasons.append("TIGHT_SPREAD")
    else: reasons.append("SPREAD_TOO_WIDE")

    if fresh<=cfg.max_fresh_seconds: score+=10; reasons.append("FRESH_MICROSTRUCTURE")
    else: reasons.append("STALE_MICROSTRUCTURE")

    if oi_change_pct<=cfg.max_oi_rise_pct: score+=10; reasons.append("OI_CONFIRMATION")
    else: reasons.append("OI_EXPANSION_BLOCK")

    cvd=abs(_f(getattr(signal,"cvd_pressure",0)))
    if cvd>=0.20: score+=15; reasons.append("STRONG_CVD_PRESSURE")
    elif cvd>=0.08: score+=8; reasons.append("CVD_CONFIRMATION")
    else: reasons.append("CVD_WEAK")

    bias=str(getattr(signal,"five_min_bias","UNKNOWN"))
    action=str(getattr(signal,"action","NO_TRADE"))
    if (action=="LONG" and bias=="BULLISH") or (action=="SHORT" and bias=="BEARISH"):
        score+=10; reasons.append("5M_BIAS_ALIGNED")
    elif bias=="NEUTRAL":
        score+=4; reasons.append("5M_BIAS_NEUTRAL")
    else:
        reasons.append("5M_BIAS_CONFLICT")

    if daily_loss_fraction>=cfg.max_daily_loss_fraction:
        return EdgeDecision(False,score,tuple(reasons+["DAILY_LOSS_CIRCUIT_BREAKER"]),"NO_TRADE")
    if consecutive_losses>=cfg.max_consecutive_losses:
        return EdgeDecision(False,score,tuple(reasons+["CONSECUTIVE_LOSS_CIRCUIT_BREAKER"]),"NO_TRADE")

    blockers=[]
    if confidence<cfg.min_confidence: blockers.append("CONFIDENCE_GATE")
    if rr<cfg.min_rr: blockers.append("RR_GATE")
    if spread_bps>cfg.max_spread_bps: blockers.append("SPREAD_GATE")
    if fresh>cfg.max_fresh_seconds: blockers.append("FRESHNESS_GATE")
    if oi_change_pct>cfg.max_oi_rise_pct: blockers.append("OI_GATE")
    if (action=="LONG" and bias=="BEARISH") or (action=="SHORT" and bias=="BULLISH"):
        blockers.append("BIAS_CONFLICT")

    allowed=score>=cfg.min_score and not blockers
    return EdgeDecision(allowed,round(score,2),tuple(reasons+blockers),
                        action if allowed else "NO_TRADE")
