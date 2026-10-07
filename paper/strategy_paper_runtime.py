"""Strategy paper runtime: signal + risk + paper execution only.

No live exchange submission is performed here.
"""
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from decision_engine.engine import make_decision
from decision_engine.schema import MarketEvidence
from paper.paper_engine import PaperEngine
from risk.limits import RiskEngine

RUNTIME_FILE = Path(__file__).resolve().parents[1] / "data" / "paper_runtime.json"

@dataclass(frozen=True)
class PaperRuntimeSnapshot:
    timestamp: int
    symbol: str
    decision: str
    score: float
    confidence: float
    allowed: bool
    reason_codes: tuple[str, ...]
    mark_price: float
    position: dict[str, Any] | None


def run_once(evidence: MarketEvidence, mark_price: float, usd_inr: float, notional_inr: float = 5000.0) -> PaperRuntimeSnapshot:
    """Evaluate a decision and, only for LONG/SHORT, paper-execute it when risk allows."""
    if mark_price <= 0 or usd_inr <= 0:
        raise ValueError("mark_price and usd_inr must be positive")

    decision = make_decision(evidence)
    paper = PaperEngine(symbol=evidence.symbol)

    # Paper engine supports symmetric LONG/SHORT opens and opposite-side closes.
    if decision.decision not in {"LONG", "SHORT"} or paper.has_position():
        snapshot = _snapshot(decision, evidence.symbol, mark_price, paper)
        _persist(snapshot)
        return snapshot

    risk = RiskEngine(
        live_trading=False,
        max_positions=1,
        max_position_notional_inr=notional_inr,
        max_daily_loss_inr=250,
        max_order_notional_inr=notional_inr,
        kill_switch=True,
        contract_value_btc=0.001,
    )
    check = risk.check(
        order_notional_inr=notional_inr,
        current_positions=1 if paper.has_position() else 0,
        daily_loss_inr=0,
        btc_usd_price=mark_price,
        usd_inr=usd_inr,
        kill_switch_active=False,
    )

    if check.allowed and check.position_size is not None:
        size = check.position_size
        paper.submit(
            side="buy" if decision.decision == "LONG" else "sell",
            quantity=size.quantity_btc,
            price=mark_price,
            notional_inr=size.inr_notional,
        )

    snapshot = _snapshot(decision, evidence.symbol, mark_price, paper)
    _persist(snapshot)
    return snapshot


def _snapshot(decision, symbol: str, mark_price: float, paper: PaperEngine) -> PaperRuntimeSnapshot:
    position = asdict(paper.position) if paper.position is not None else None
    return PaperRuntimeSnapshot(
        timestamp=int(datetime.now(timezone.utc).timestamp()),
        symbol=symbol,
        decision=decision.decision,
        score=decision.score,
        confidence=decision.confidence,
        allowed=decision.allowed,
        reason_codes=decision.reason_codes,
        mark_price=mark_price,
        position=position,
    )


def _persist(snapshot: PaperRuntimeSnapshot) -> None:
    RUNTIME_FILE.parent.mkdir(parents=True, exist_ok=True)
    RUNTIME_FILE.write_text(json.dumps(asdict(snapshot), indent=2), encoding="utf-8")


if __name__ == "__main__":
    print("Import run_once() from the live/replay data pipeline; no exchange orders are sent.")
