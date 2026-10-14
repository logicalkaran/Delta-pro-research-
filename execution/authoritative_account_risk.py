"""Fail-closed authoritative account-state gate. No exchange mutations."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
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


def _anchors(journal: Any, now_ms: int) -> tuple[float, float, float]:
    """Derive UTC drawdown anchors from timestamped authoritative equity samples.

    The hourly writer emits AUTHORITATIVE_EQUITY_ANCHOR, not three synthetic
    anchor event types. Use the first observed equity sample in the current UTC
    day/week and the maximum observed equity across history. Missing current
    period coverage remains a hard rejection; no anchor is fabricated.
    """
    accepted: list[tuple[int, float]] = []
    supported_types = {
        "AUTHORITATIVE_EQUITY_ANCHOR", "DAILY_EQUITY_ANCHOR",
        "WEEKLY_EQUITY_ANCHOR", "PEAK_EQUITY_ANCHOR",
    }
    for event in journal.replay():
        if not isinstance(event, dict) or event.get("event_type") not in supported_types:
            continue
        payload = event.get("payload", {})
        if not isinstance(payload, dict):
            raise AuthoritativeStateError("INVALID_EQUITY_ANCHOR_PAYLOAD")
        value = _num(payload.get("equity"), "anchor_equity")
        observed = payload.get("observed_at_ms")
        if observed is None:
            ts_ns = event.get("ts_ns")
            if isinstance(ts_ns, bool) or not isinstance(ts_ns, (int, float)):
                raise AuthoritativeStateError("MISSING_EQUITY_ANCHOR_TIMESTAMP")
            observed = int(ts_ns) // 1_000_000
        timestamp = _num(observed, "anchor_timestamp_ms")
        if timestamp < 0 or timestamp > now_ms + 1_000:
            continue
        accepted.append((int(timestamp), value))

    current_day = datetime.fromtimestamp(now_ms / 1000, timezone.utc).date()
    current_week = current_day.isocalendar()[:2]
    day_rows = [
        (ts, equity) for ts, equity in accepted
        if datetime.fromtimestamp(ts / 1000, timezone.utc).date() == current_day
    ]
    week_rows = [
        (ts, equity) for ts, equity in accepted
        if datetime.fromtimestamp(ts / 1000, timezone.utc).date().isocalendar()[:2] == current_week
    ]
    missing = []
    if not day_rows:
        missing.append("day")
    if not week_rows:
        missing.append("week")
    if not accepted:
        missing.append("peak")
    if missing:
        raise AuthoritativeStateError("MISSING_DRAWDOWN_ANCHORS:" + ",".join(missing))
    day_anchor = min(day_rows, key=lambda row: row[0])[1]
    week_anchor = min(week_rows, key=lambda row: row[0])[1]
    peak_anchor = max(equity for _, equity in accepted)
    return day_anchor, week_anchor, peak_anchor


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
        day, week, peak = _anchors(journal, now)
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
