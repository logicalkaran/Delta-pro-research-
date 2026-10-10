from .schema import MarketEvidence, DecisionResult
from .scoring import calculate_score
from .gates import quality_gate


def make_decision(e: MarketEvidence) -> DecisionResult:

    allowed, gate_reason = quality_gate(e)

    if not allowed:
        return DecisionResult(
            symbol=e.symbol,
            decision="SKIP",
            score=0.0,
            confidence=0.0,
            allowed=False,
            reason_codes=(gate_reason,),
        )

    score, reasons = calculate_score(e)

    if score >= 5:
        decision = "LONG"
    elif score <= -5:
        decision = "SHORT"
    elif abs(score) >= 2:
        decision = "HOLD"
    else:
        decision = "SKIP"

    confidence = min(abs(score) / 10.0, 1.0)

    reasons.append(gate_reason)

    return DecisionResult(
        symbol=e.symbol,
        decision=decision,
        score=round(score, 2),
        confidence=round(confidence, 3),
        allowed=decision in ("LONG", "SHORT"),
        reason_codes=tuple(reasons),
    )
