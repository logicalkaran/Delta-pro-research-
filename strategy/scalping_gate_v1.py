"""Cost-aware BTC scalping scorer and hard-gate layer."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any
from .scalping_features_v1 import ScalpingFeatures

@dataclass(frozen=True)
class ScalpingGateConfig:
    min_score: float = 6.0
    min_rr: float = 1.5
    max_spread_bps: float = 5.0
    min_move_to_cost: float = 3.0
    maker_fee_bps: float = 2.0
    taker_fee_bps: float = 5.0
    slippage_bps: float = 2.0
    stop_atr_buffer: float = 0.35
    risk_fraction: float = 0.005
    max_daily_r: float = 3.0
    max_consecutive_losses: int = 3

@dataclass(frozen=True)
class ScalpingDecision:
    decision: str
    side: str
    score: float
    confidence: float
    allowed: bool
    entry: float
    stop: float | None
    target: float | None
    risk_distance: float | None
    reward_distance: float | None
    rr: float | None
    expected_move_bps: float
    forecast_source: str
    round_trip_cost_bps: float
    cost_multiple: float
    hard_gates: tuple[str, ...]
    reasons: tuple[str, ...]
    rejected: tuple[str, ...]
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

def _f(value: Any, default: float = 0.0) -> float:
    try: return float(value)
    except (TypeError, ValueError): return default

def round_trip_cost_bps(cfg: ScalpingGateConfig, *, maker_entry: bool = True) -> float:
    entry_fee = cfg.maker_fee_bps if maker_entry else cfg.taker_fee_bps
    return entry_fee + cfg.taker_fee_bps + 2.0 * cfg.slippage_bps

def _directional_score(side: str, f: ScalpingFeatures) -> tuple[float, list[str]]:
    score, reasons, sign = 0.0, [], 1.0 if side == "LONG" else -1.0
    sweep = f.sweep.direction
    if (side == "LONG" and sweep == "LOW_SWEEP") or (side == "SHORT" and sweep == "HIGH_SWEEP"):
        if f.sweep.valid:
            score += 3.0; reasons.append("LIQUIDITY_SWEEP_ALIGNED")
            if f.sweep.rejection >= 0.50: score += 0.5; reasons.append("SWEEP_REJECTION_STRONG")
    elif (side == "LONG" and sweep == "HIGH_SWEEP") or (side == "SHORT" and sweep == "LOW_SWEEP"):
        score -= 3.0; reasons.append("LIQUIDITY_SWEEP_OPPOSED")
    if (side == "LONG" and f.fvg.direction == "BULLISH") or (side == "SHORT" and f.fvg.direction == "BEARISH"):
        score += 1.5; reasons.append("FVG_ALIGNED")
    elif f.fvg.direction in ("BULLISH", "BEARISH"):
        score -= 1.5; reasons.append("FVG_OPPOSED")
    cvd = max(-1.0, min(1.0, f.cvd.delta_ratio)); aligned = cvd * sign
    if aligned >= 0.20: score += 2.0; reasons.append("CVD_ALIGNED")
    elif aligned >= 0.08: score += 1.0; reasons.append("CVD_SUPPORTIVE")
    elif aligned <= -0.20: score -= 2.0; reasons.append("CVD_OPPOSED")
    obi = max(-1.0, min(1.0, f.imbalance.imbalance)); aligned = obi * sign
    if aligned >= 0.20: score += 1.5; reasons.append("BOOK_IMBALANCE_ALIGNED")
    elif aligned >= 0.08: score += 0.75; reasons.append("BOOK_IMBALANCE_SUPPORTIVE")
    elif aligned <= -0.20: score -= 1.5; reasons.append("BOOK_IMBALANCE_OPPOSED")
    if 0.75 <= f.displacement_atr <= 2.50: score += 1.0; reasons.append("DISPLACEMENT_VALID")
    elif f.displacement_atr > 3.50: score -= 1.0; reasons.append("DISPLACEMENT_OVEREXTENDED")
    if f.volume_z >= 1.0: score += 0.5; reasons.append("VOLUME_EXPANSION")
    return score, reasons

def evaluate(features: ScalpingFeatures, *, side: str, entry: float, target: float | None = None,
             forecast_edge_bps: float | None = None, forecast_source: str = "independent_forecast",
             prior_daily_r: float = 0.0, consecutive_losses: int = 0,
             cfg: ScalpingGateConfig = ScalpingGateConfig(), maker_entry: bool = True) -> ScalpingDecision:
    side = str(side).upper(); entry = _f(entry)
    if side not in {"LONG", "SHORT"}:
        return ScalpingDecision("SKIP", side, 0.0, 0.0, False, entry, None, None, None, None, None,
                                0.0, "none", round_trip_cost_bps(cfg, maker_entry=maker_entry), 0.0, (), (), ("INVALID_SIDE",))
    rejected, hard, reasons = [], [], []
    if entry <= 0: rejected.append("INVALID_ENTRY")
    if features.atr <= 0: rejected.append("ATR_UNAVAILABLE")
    if not features.imbalance.valid: rejected.append("ORDERBOOK_UNAVAILABLE")
    if features.cvd.known_volume <= 0: rejected.append("CVD_UNAVAILABLE")
    spread_bps = features.imbalance.spread_bps
    if spread_bps is None: rejected.append("SPREAD_UNAVAILABLE")
    elif spread_bps <= cfg.max_spread_bps: hard.append("SPREAD_OK")
    else: rejected.append("SPREAD_TOO_WIDE")
    if prior_daily_r <= -cfg.max_daily_r: rejected.append("DAILY_LOSS_CAP_REACHED")
    else: hard.append("DAILY_RISK_OK")
    if consecutive_losses >= cfg.max_consecutive_losses: rejected.append("CONSECUTIVE_LOSS_HALT")
    else: hard.append("LOSS_STREAK_OK")
    cost_bps = round_trip_cost_bps(cfg, maker_entry=maker_entry)
    stop = risk = reward = rr = None
    if entry > 0 and features.atr > 0:
        if side == "LONG":
            level = features.sweep.level if features.sweep.direction == "LOW_SWEEP" else entry - features.atr
            stop = level - cfg.stop_atr_buffer * features.atr; risk = entry - stop
        else:
            level = features.sweep.level if features.sweep.direction == "HIGH_SWEEP" else entry + features.atr
            stop = level + cfg.stop_atr_buffer * features.atr; risk = stop - entry
        if risk is not None and risk > 0:
            if target is None: rejected.append("TARGET_REQUIRED")
            else:
                target = _f(target); reward = target-entry if side=="LONG" else entry-target
                if reward <= 0: rejected.append("TARGET_ON_WRONG_SIDE")
                else:
                    rr = reward/risk
                    if rr >= cfg.min_rr: hard.append("RR_OK")
                    else: rejected.append("RR_BELOW_MINIMUM")
    score, score_reasons = _directional_score(side, features); reasons.extend(score_reasons)
    expected_move_bps = max(0.0, _f(forecast_edge_bps)) if forecast_edge_bps is not None else 0.0
    if forecast_edge_bps is None:
        rejected.append("INDEPENDENT_FORECAST_REQUIRED")
        forecast_source = "none"
    elif expected_move_bps <= 0:
        rejected.append("FORECAST_EDGE_NON_POSITIVE")
    multiple = expected_move_bps/cost_bps if cost_bps > 0 else 0.0
    if expected_move_bps >= cfg.min_move_to_cost*cost_bps: hard.append("EXPECTED_MOVE_COST_BUFFER_OK")
    else: rejected.append("EXPECTED_MOVE_BELOW_COST_BUFFER")
    if score >= cfg.min_score: reasons.append("SCORE_THRESHOLD_MET")
    else: rejected.append("SCORE_BELOW_THRESHOLD")
    allowed = not rejected and score >= cfg.min_score
    return ScalpingDecision(side if allowed else "SKIP", side, round(score,3),
        round(min(1.0,max(0.0,score/max(cfg.min_score+2.0,1.0))),3), allowed, entry,
        round(stop,8) if stop is not None else None, round(target,8) if target is not None else None,
        round(risk,8) if risk is not None else None, round(reward,8) if reward is not None else None,
        round(rr,4) if rr is not None else None, round(expected_move_bps,4), str(forecast_source), round(cost_bps,4),
        round(multiple,4), tuple(hard), tuple(reasons), tuple(rejected))
