from dataclasses import dataclass
from typing import Literal


Decision = Literal["LONG", "SHORT", "HOLD", "SKIP"]


@dataclass(frozen=True)
class MarketEvidence:
    symbol: str

    fisher: float
    rsi: float

    smc_bias: str
    trend: str
    volume_quality: str

    data_quality: float
    evidence_quality: float


@dataclass(frozen=True)
class DecisionResult:
    symbol: str
    decision: Decision
    score: float
    confidence: float
    allowed: bool
    reason_codes: tuple[str, ...]
