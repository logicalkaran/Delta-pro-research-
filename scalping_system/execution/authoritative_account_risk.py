"""Fail-closed authoritative account-state gate. No exchange mutations."""
from __future__ import annotations
from dataclasses import asdict, dataclass
import math
import time
from typing import Any

from risk.orchestration_oracle import OrderIntent, PortfolioSnapshot, RiskLimits, evaluate


@dataclass(frozen=True)
class AuthoritativeRiskResult:
    verdict: str
    reason: str
    approved_signed_quantity_btc: float
    current_position_btc: float | None = None
    post_trade_exposure_btc: float | None = None
    stress_equity: float | None = None
    stress_maintenance_margin: float | None = None
    observed_at_ms: int | None = None
    drawdowns: dict[str, float] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AuthoritativeStateError(RuntimeError):
    pass


def _num(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise AuthoritativeStateError("INVALID_" + field.upper())
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise AuthoritativeStateError("INVALID_" + field.upper()) from None
    if not math.isfinite(result):
        raise AuthoritativeStateError("INVALID_" + field.upper())
    return result


def _anchors(journal: Any) -> tuple[float, float, float]:
    names = {"DAILY_EQUITY_ANCHOR": "day", "WEEKLY_EQUITY_ANCHOR": "week",
             "PEAK_EQUITY_ANCHOR": "peak"}
    latest: dict[str, tuple[int, float]] = {}
    for event in journal.replay():
        key = names.get(event.get("event_type"))
        if key is None:
            continue
        payload = event.get("payload", {})
        value = _num(payload.get("equity"), key + "_anchor_equity")
        seq = int(event.get("seq", 0))
        if key not in latest or seq > latest[key][0]:
            latest[key] = (seq, value)
    missing = [key for key in ("day", "week", "peak") if key not in latest]
    if missing:
        raise AuthoritativeStateError("MISSING_DRAWDOWN_ANCHORS:" + ",".join(missing))
    return latest["day"][1], latest["week"][1], latest["peak"][1]


def _position_btc(adapter: Any, symbol: str) -> float:
    payload = adapter.get_positions()
    if not isinstance(payload, dict) or payload.get("success") is False:
        raise AuthoritativeStateError("POSITION_STATE_UNAVAILABLE")
    rows = payload.get("result")
    if isinstance(rows, dict):
        rows = [rows]
    if not isinstance(rows, list):
        raise AuthoritativeStateError("POSITION_PAYLOAD_MALFORMED")
    matches = [r for r in rows if isinstance(r, dict) and
               (r.get("product_symbol") == symbol or r.get("symbol") == symbol)]
    if not matches:
        return 0.0
    total = 0.0
    for row in matches:
        field = "signed_position_btc" if "signed_position_btc" in row else (
            "position_btc" if "position_btc" in row else None)
        if field is None:
            # Delta inverse contracts cannot safely be assumed to equal BTC.
            raise AuthoritativeStateError("POSITION_BTC_DENOMINATION_UNVERIFIED")
        total += _num(row[field], "position_btc")
    return total


def evaluate_authoritative_intent(*, adapter: Any, journal: Any, symbol: str,
        mark_price: float, proposed_signed_quantity_btc: float,
        now_ms: int | None = None, max_state_age_ms: int = 5_000,
        limits: RiskLimits | None = None, market_data_age_seconds: float = 0.0,
        websocket_latency_ms: float = 0.0, memory_mb: float = 0.0,
        kill_switch: bool = False) -> AuthoritativeRiskResult:
    """Missing/stale account state or historical anchors always rejects."""
    now = int(time.time() * 1000) if now_ms is None else int(now_ms)
    try:
        state = adapter.account_state()
        observed = int(state.observed_at_ms)
        if now - observed > max_state_age_ms or observed - now > 1_000:
            return AuthoritativeRiskResult("REJECTED", "STALE_DATA_REJECTION", 0.0,
                                           observed_at_ms=observed)
        if not state.complete:
            return AuthoritativeRiskResult("REJECTED",
                "MISSING_ACCOUNT_FIELDS:" + ",".join(state.missing_fields), 0.0,
                observed_at_ms=observed)
        available = _num(state.available_balance, "available_balance")
        equity = _num(state.equity, "equity")
        maintenance = _num(state.maintenance_margin, "maintenance_margin")
        if available < 0 or equity <= 0 or maintenance < 0:
            raise AuthoritativeStateError("INVALID_ACCOUNT_RISK_VALUES")
        current = _position_btc(adapter, symbol)
        mark = _num(mark_price, "mark_price")
        proposed = _num(proposed_signed_quantity_btc, "proposed_quantity_btc")
        if mark <= 0 or proposed == 0:
            raise AuthoritativeStateError("INVALID_MARK_OR_ORDER_QUANTITY")
        day, week, peak = _anchors(journal)
        net = current + proposed

        # Direct conservative shock gate using authoritative equity and MM.
        stress_equity = equity - abs(net) * mark * 0.05
        stress_mm = maintenance * 1.05
        if stress_equity <= 0 or stress_mm >= stress_equity * 0.80:
            return AuthoritativeRiskResult("REJECTED", "STRESS_MARGIN_BUFFER_BREACH",
                0.0, current, net, stress_equity, stress_mm, observed)

        notional = abs(current) * mark
        if notional <= 0 or maintenance <= 0:
            raise AuthoritativeStateError("MAINTENANCE_MARGIN_RATE_UNVERIFIABLE")
        snapshot = PortfolioSnapshot(
            mark_price=mark, account_equity=equity, current_position_btc=current,
            maintenance_margin_rate=maintenance / notional,
            day_start_equity=day, week_start_equity=week, peak_equity=peak,
            market_data_age_seconds=market_data_age_seconds,
            websocket_latency_ms=websocket_latency_ms, memory_mb=memory_mb,
            kill_switch=kill_switch)
        decision = evaluate(snapshot, OrderIntent(proposed), limits or RiskLimits())
        return AuthoritativeRiskResult(decision.verdict.value,
            ",".join(decision.reason_codes), decision.approved_signed_quantity_btc,
            current, decision.net_exposure_btc, decision.stress_equity,
            decision.stress_maintenance_margin, observed,
            {"daily": decision.daily_drawdown_fraction or 0.0,
             "weekly": decision.weekly_drawdown_fraction or 0.0,
             "peak_to_trough": decision.peak_drawdown_fraction or 0.0})
    except AuthoritativeStateError as exc:
        return AuthoritativeRiskResult("REJECTED", str(exc), 0.0)
    except Exception as exc:
        return AuthoritativeRiskResult("REJECTED",
            "AUTHORITATIVE_STATE_ERROR:" + type(exc).__name__, 0.0)
