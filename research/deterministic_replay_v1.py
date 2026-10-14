"""Deterministic point-in-time event replay primitives. Research-only; never routes live orders.

Events are consumed in local ingestion order, not sorted by exchange timestamps.
No live market data is written by this module.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Protocol, Sequence
import hashlib
import json
import math


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    IOC = "IOC"


@dataclass(frozen=True, slots=True)
class MarketEvent:
    local_ingestion_ns: int
    exchange_ns: int | None
    event_type: str
    payload: dict[str, Any]
    sequence: int = 0

    def __post_init__(self):
        if self.local_ingestion_ns <= 0:
            raise ValueError("local_ingestion_ns must be positive")
        if self.exchange_ns is not None and self.exchange_ns <= 0:
            raise ValueError("exchange_ns must be positive or None")
        if not self.event_type:
            raise ValueError("event_type is required")


@dataclass(frozen=True, slots=True)
class OrderIntent:
    strategy_id: str
    side: Side
    quantity: float
    order_type: OrderType
    time_in_force: str = "IOC"
    limit_price: float | None = None
    ttl_ms: int = 1000

    def __post_init__(self):
        if not self.strategy_id:
            raise ValueError("strategy_id is required")
        if not math.isfinite(self.quantity) or self.quantity <= 0:
            raise ValueError("quantity must be finite and positive")
        if self.order_type == OrderType.LIMIT and (self.limit_price is None or not math.isfinite(self.limit_price) or self.limit_price <= 0):
            raise ValueError("LIMIT intents require a finite positive limit_price")
        if self.ttl_ms < 0:
            raise ValueError("ttl_ms must be nonnegative")
        if self.time_in_force not in {"GTC", "IOC", "FOK", "DAY"}:
            raise ValueError("unsupported time_in_force")


@dataclass(frozen=True, slots=True)
class ExecutionCosts:
    maker_fee_bps: float = 2.36
    taker_fee_bps: float = 5.90
    slippage_bps: float = 1.0
    extra_spread_bps: float = 0.0
    latency_ms: int = 100

    def __post_init__(self):
        for name in ("maker_fee_bps", "taker_fee_bps", "slippage_bps", "extra_spread_bps"):
            value = getattr(self, name)
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative")
        if self.latency_ms < 0:
            raise ValueError("latency_ms must be nonnegative")


class Strategy(Protocol):
    def on_event(self, market_data: dict[str, Any]) -> OrderIntent | None: ...


@dataclass(slots=True)
class ReplayReport:
    events_seen: int = 0
    intents_seen: int = 0
    fills: list[dict[str, Any]] = field(default_factory=list)
    rejects: list[dict[str, Any]] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)


def deterministic_event_order(events: Iterable[MarketEvent]) -> list[MarketEvent]:
    """Stable local-arrival ordering. Equal receive times use captured sequence then input order."""
    indexed = list(enumerate(events))
    if any(not isinstance(e, MarketEvent) for _, e in indexed):
        raise TypeError("all events must be MarketEvent")
    indexed.sort(key=lambda pair: (pair[1].local_ingestion_ns, pair[1].sequence, pair[0]))
    return [event for _, event in indexed]


def event_tape_digest(events: Sequence[MarketEvent]) -> str:
    """Stable digest for audit/reproducibility; payloads are hashed, not written to disk."""
    canonical = []
    for e in deterministic_event_order(events):
        canonical.append({
            "local_ingestion_ns": e.local_ingestion_ns,
            "exchange_ns": e.exchange_ns,
            "event_type": e.event_type,
            "sequence": e.sequence,
            "payload": e.payload,
        })
    raw = json.dumps(canonical, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def crossed_or_invalid_book(book: dict[str, Any]) -> bool:
    try:
        bid, ask = float(book["bid"]), float(book["ask"])
        return not (math.isfinite(bid) and math.isfinite(ask) and bid > 0 and ask >= bid)
    except (KeyError, TypeError, ValueError):
        return True


def taker_round_trip_cost_bps(costs: ExecutionCosts, spread_bps: float) -> float:
    """Two taker fees + full spread + modeled slippage on entry and exit."""
    if not math.isfinite(spread_bps) or spread_bps < 0:
        raise ValueError("spread_bps must be finite and nonnegative")
    return 2 * costs.taker_fee_bps + spread_bps + 2 * costs.slippage_bps + costs.extra_spread_bps


def net_return_bps(gross_return_bps: float, costs_bps: float) -> float:
    if not math.isfinite(gross_return_bps) or not math.isfinite(costs_bps) or costs_bps < 0:
        raise ValueError("returns must be finite and costs nonnegative")
    return gross_return_bps - costs_bps


def zero_alpha_baseline(
    trade_count: int = 10_000,
    *,
    seed: int = 20261010,
    gross_returns_bps: Sequence[float] | None = None,
    round_trip_cost_bps: float = 14.8,
) -> dict[str, Any]:
    """Deterministic coin-flip-direction baseline with fixed cost per completed round trip.

    Synthetic gross outcomes are symmetric +/- outcomes, generated from a local PRNG.
    This tests cost application/accounting; it is not a market-price-path or fill model.
    """
    import random
    if trade_count <= 0:
        raise ValueError("trade_count must be positive")
    if not math.isfinite(round_trip_cost_bps) or round_trip_cost_bps < 0:
        raise ValueError("round_trip_cost_bps must be finite and nonnegative")
    rng = random.Random(seed)
    if gross_returns_bps is None:
        # Symmetric toy outcome distribution with zero theoretical expectancy.
        gross = [rng.choice((-1.0, 1.0)) * rng.random() * 50.0 for _ in range(trade_count)]
    else:
        gross = [float(x) for x in gross_returns_bps]
        if len(gross) != trade_count:
            raise ValueError("gross_returns_bps length must equal trade_count")
        if not all(math.isfinite(x) for x in gross):
            raise ValueError("gross returns must be finite")
    net = [net_return_bps(x, round_trip_cost_bps) for x in gross]
    equity = 0.0
    curve = []
    peak = 0.0
    max_drawdown = 0.0
    for result in net:
        equity += result
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
        curve.append(equity)
    gross_mean = sum(gross) / len(gross)
    net_mean = sum(net) / len(net)
    return {
        "schema": "deterministic_replay_zero_alpha_v1",
        "research_only": True,
        "real_orders": False,
        "seed": seed,
        "trades": trade_count,
        "gross_mean_bps": gross_mean,
        "round_trip_cost_bps": round_trip_cost_bps,
        "net_mean_bps": net_mean,
        "expected_net_mean_bps_if_zero_gross_edge": -round_trip_cost_bps,
        "cost_accounting_identity_pass": all(abs((g - n) - round_trip_cost_bps) < 1e-9 for g, n in zip(gross, net)),
        "equity_curve_monotonic_down": all(curve[i] <= curve[i-1] for i in range(1, len(curve))),
        "max_drawdown_bps": max_drawdown,
        "equity_curve": curve,
        "note": "A zero-alpha realized curve need not decline monotonically; random gross outcomes can temporarily profit. Verify expected net edge and exact cost accounting instead.",
    }


def replay_events(events: Iterable[MarketEvent], strategy: Strategy, *, costs: ExecutionCosts = ExecutionCosts()) -> ReplayReport:
    """Minimal deterministic strategy harness. This first milestone emits intents, not simulated fills."""
    report = ReplayReport()
    last_local_ns = 0
    for event in deterministic_event_order(events):
        if event.local_ingestion_ns < last_local_ns:
            raise AssertionError("local arrival order regressed")
        last_local_ns = event.local_ingestion_ns
        report.events_seen += 1
        # Deliberately provide only the current event; never provide future arrays or portfolio state.
        view = {
            "local_ingestion_ns": event.local_ingestion_ns,
            "exchange_ns": event.exchange_ns,
            "event_type": event.event_type,
            "payload": dict(event.payload),
        }
        intent = strategy.on_event(view)
        if intent is None:
            continue
        report.intents_seen += 1
        if not isinstance(intent, OrderIntent):
            report.rejects.append({"local_ingestion_ns": event.local_ingestion_ns, "reason": "INVALID_INTENT_TYPE"})
            continue
        # Execution remains deliberately disabled until the latency/depth/queue state machine is independently validated.
        report.rejects.append({
            "local_ingestion_ns": event.local_ingestion_ns,
            "strategy_id": intent.strategy_id,
            "reason": "EXECUTION_SIMULATOR_NOT_YET_CONNECTED",
            "order_type": intent.order_type.value,
            "latency_ms_configured": costs.latency_ms,
        })
    return report

def replay_execution(
    events: Iterable[MarketEvent],
    strategy: Strategy,
    *,
    costs: ExecutionCosts = ExecutionCosts(),
    quantity_cap: float = 1.0,
) -> ReplayReport:
    """Event-driven execution simulation using only book/trade state available at each step.

    Market orders execute against the last known quote when synthetic arrival latency expires.
    Passive limit fills require observed aggressive volume at the exact limit price to exceed
    displayed queue ahead plus our quantity. Partial fills and hidden queue priority are not
    inferred. Missing/stale quote validation is intentionally strict.
    """
    if not math.isfinite(quantity_cap) or quantity_cap <= 0:
        raise ValueError("quantity_cap must be finite and positive")
    report = ReplayReport()
    bid = ask = bid_size = ask_size = None
    bid_levels: list[tuple[float, float]] = []
    ask_levels: list[tuple[float, float]] = []
    pending: list[dict[str, Any]] = []
    active_limits: list[dict[str, Any]] = []
    last_local_ns = 0

    def get_book():
        return {"bid": bid, "ask": ask, "bid_size": bid_size, "ask_size": ask_size}

    def add_fill(intent: OrderIntent, price: float, route: str, at_ns: int, qty: float,
                 ref_mid: float | None, order_arrival_ns: int | None = None):
        fee = costs.maker_fee_bps if route == "MAKER" else costs.taker_fee_bps
        slip = 0.0 if route == "MAKER" else costs.slippage_bps
        report.fills.append({
            "strategy_id": intent.strategy_id, "side": intent.side.value,
            "quantity": qty, "fill_price": price, "route": route,
            "fee_bps": fee, "modeled_slippage_bps": slip,
            "arrival_local_ns": order_arrival_ns if order_arrival_ns is not None else at_ns,
            "fill_local_ns": at_ns, "reference_mid": ref_mid,
            "reference_to_fill_bps": ((price / ref_mid - 1.0) * 10000.0 if ref_mid else None),
            "status": "FILLED", "research_only": True,
        })

    for event in deterministic_event_order(events):
        now = event.local_ingestion_ns
        if now < last_local_ns:
            raise AssertionError("event time regression")
        last_local_ns = now
        # Process arrivals against the PREVIOUS event's book. Never use the current event
        # to retroactively give an order a better arrival quote.
        still_pending = []
        for item in pending:
            intent = item["intent"]
            arrival_ns = item["arrival_ns"]
            if now < arrival_ns:
                still_pending.append(item)
                continue
            book = get_book()
            if crossed_or_invalid_book(book):
                report.rejects.append({"strategy_id": intent.strategy_id, "reason": "NO_VALID_BOOK_AT_ARRIVAL", "arrival_local_ns": arrival_ns})
                continue
            mid = (float(bid) + float(ask)) / 2.0
            qty = min(intent.quantity, quantity_cap)
            if intent.order_type in {OrderType.MARKET, OrderType.IOC}:
                ref = float(ask if intent.side == Side.BUY else bid)
                raw_price = ref * (1.0 + costs.slippage_bps / 10000.0 if intent.side == Side.BUY else 1.0 - costs.slippage_bps / 10000.0)
                depth = float(ask_size if intent.side == Side.BUY else bid_size)
                if depth + 1e-12 < qty:
                    report.rejects.append({"strategy_id": intent.strategy_id, "reason": "INSUFFICIENT_TOP_OF_BOOK_DEPTH", "arrival_local_ns": arrival_ns})
                else:
                    add_fill(intent, raw_price, "TAKER", arrival_ns, qty, mid)
                continue
            limit = float(intent.limit_price)
            marketable = (intent.side == Side.BUY and limit >= float(ask)) or (intent.side == Side.SELL and limit <= float(bid))
            if marketable:
                ref = float(ask if intent.side == Side.BUY else bid)
                if (intent.side == Side.BUY and limit >= ref) or (intent.side == Side.SELL and limit <= ref):
                    add_fill(intent, ref, "TAKER", arrival_ns, qty, mid)
                continue
            levels = bid_levels if intent.side == Side.BUY else ask_levels
            queue_ahead = next((size for price, size in levels if abs(price - limit) < 1e-9), None)
            # Only model passive queues at the best price with observed displayed size.
            best = float(bid if intent.side == Side.BUY else ask)
            if abs(limit - best) > 1e-9 or queue_ahead is None:
                report.rejects.append({"strategy_id": intent.strategy_id, "reason": "LIMIT_LEVEL_NOT_OBSERVED_AT_ARRIVAL", "arrival_local_ns": arrival_ns})
                continue
            active_limits.append({"intent": intent, "arrival_ns": arrival_ns, "limit": limit,
                                  "queue_ahead": max(0.0, float(queue_ahead)), "qty": qty,
                                  "traded_ahead": 0.0, "expires_ns": arrival_ns + intent.ttl_ms * 1_000_000})
        pending = still_pending

        # Apply the current event only after due orders have been placed against prior state.
        msg = event.payload
        typ = msg.get("type", event.event_type)
        if typ == "ob_l1":
            try:
                b, a = float(msg["bp"]), float(msg["ap"])
                bs, ass = float(msg.get("bs", 0)), float(msg.get("as", 0))
                if b > 0 and a >= b and bs >= 0 and ass >= 0 and all(map(math.isfinite, (b,a,bs,ass))):
                    bid, ask, bid_size, ask_size = b, a, bs, ass
                    bid_levels, ask_levels = [(b, bs)], [(a, ass)]
            except (KeyError, TypeError, ValueError):
                pass
        elif typ == "ob_l2":
            def parse_levels(raw):
                result = []
                if isinstance(raw, list):
                    for level in raw:
                        try:
                            price, size = float(level[0]), float(level[1])
                            if price > 0 and size >= 0 and math.isfinite(price) and math.isfinite(size):
                                result.append((price, size))
                        except (TypeError, ValueError, IndexError):
                            continue
                return result
            bs, ass = parse_levels(msg.get("b")), parse_levels(msg.get("a"))
            if bs and ass:
                b, bq = max(bs, key=lambda x: x[0])
                a, aq = min(ass, key=lambda x: x[0])
                if a >= b:
                    bid, ask, bid_size, ask_size = b, a, bq, aq
                    bid_levels, ask_levels = bs, ass
        elif typ == "trades":
            try:
                price, size, side = float(msg["p"]), float(msg["s"]), msg.get("r")
                if math.isfinite(price) and math.isfinite(size) and size > 0 and side in {"m", "t"}:
                    survivors = []
                    for order in active_limits:
                        intent = order["intent"]
                        is_aggressor_against_order = (intent.side == Side.BUY and side == "m") or (intent.side == Side.SELL and side == "t")
                        if now > order["expires_ns"]:
                            report.rejects.append({"strategy_id": intent.strategy_id, "reason": "LIMIT_EXPIRED_UNFILLED"})
                            continue
                        touched_exact_tier = abs(price - order["limit"]) < 1e-9
                        traded_through = (
                            (intent.side == Side.BUY and side == "m" and price < order["limit"])
                            or (intent.side == Side.SELL and side == "t" and price > order["limit"])
                        )
                        if is_aggressor_against_order and touched_exact_tier:
                            order["traded_ahead"] += size
                            if order["traded_ahead"] >= order["queue_ahead"] + order["qty"]:
                                add_fill(intent, order["limit"], "MAKER", now, order["qty"], ((bid + ask) / 2.0 if bid is not None and ask is not None else None), order_arrival_ns=order["arrival_ns"])
                                continue
                        # Conservative trade-through fallback: a trade beyond the limit in
                        # the adverse direction is evidence the resting limit was executable.
                        # Mere touch is never sufficient; fills remain at the limit price.
                        if is_aggressor_against_order and traded_through:
                            add_fill(intent, order["limit"], "MAKER", now, order["qty"], ((bid + ask) / 2.0 if bid is not None and ask is not None else None), order_arrival_ns=order["arrival_ns"])
                            continue
                        survivors.append(order)
                    active_limits = survivors
            except (KeyError, TypeError, ValueError):
                pass

        report.events_seen += 1
        view = {
            "local_ingestion_ns": now, "exchange_ns": event.exchange_ns,
            "event_type": typ, "payload": dict(msg), "book": get_book(),
        }
        intent = strategy.on_event(view)
        if intent is not None:
            report.intents_seen += 1
            if not isinstance(intent, OrderIntent):
                report.rejects.append({"local_ingestion_ns": now, "reason": "INVALID_INTENT_TYPE"})
            else:
                pending.append({"intent": intent, "arrival_ns": now + costs.latency_ms * 1_000_000})
    # Do not fabricate fills after the final event: there is no new evidence of arrival or queue depletion.
    report.diagnostics.append("EVENT-DRIVEN SIMULATION; no live orders; no persistent market-data writes.")
    report.diagnostics.append("LIMIT queue model uses displayed best-level size and exact-price aggressive trades; hidden queue/partial fills remain unmodeled.")
    return report

def _epoch_ns(value: Any, *, exchange: bool = False) -> int | None:
    """Normalize epoch seconds/ms/us/ns. Exchange timestamps commonly arrive in microseconds."""
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if number <= 0:
        return None
    if number >= 100_000_000_000_000_000:
        return number
    if number >= 100_000_000_000_000:
        return number * 1_000
    if number >= 100_000_000_000:
        return number * 1_000_000
    if number >= 1_000_000_000:
        return number * 1_000_000_000
    return None


def delta_record_to_event(record: dict[str, Any], sequence: int = 0) -> MarketEvent:
    """Strict adapter for existing Delta JSONL records with a local receive timestamp.

    It refuses to substitute exchange time for missing local receive time. That omission
    makes point-in-time replay impossible without inventing when the data became available.
    """
    from datetime import datetime, timezone

    if not isinstance(record, dict):
        raise TypeError("record must be a dict")
    message = record.get("message", record)
    if not isinstance(message, dict):
        raise ValueError("record message must be a dict")
    received = record.get("received_at")
    if not isinstance(received, str) or not received.strip():
        # Some newer collectors may supply an integer local receive timestamp explicitly.
        local_ns = _epoch_ns(record.get("receive_epoch_ns"))
        if local_ns is None:
            raise ValueError("missing local ingestion timestamp; refusing exchange-time fallback")
    else:
        try:
            parsed = datetime.fromisoformat(received.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise ValueError("received_at must include timezone")
            local_ns = int(parsed.astimezone(timezone.utc).timestamp() * 1_000_000_000)
        except (ValueError, OverflowError, OSError) as exc:
            raise ValueError("invalid received_at timestamp") from exc
    # Trade execution time uses t; book updates use ts. These are descriptive timestamps,
    # not the replay clock. The local ingestion timestamp remains authoritative.
    exchange_value = message.get("t") if message.get("type") == "trades" else message.get("ts")
    exchange_ns = _epoch_ns(exchange_value)
    return MarketEvent(
        local_ingestion_ns=local_ns,
        exchange_ns=exchange_ns,
        event_type=str(message.get("type", "unknown")),
        payload=dict(message),
        sequence=int(sequence),
    )

def visible_events_at_time(events: Iterable[MarketEvent], engine_local_ns: int) -> list[MarketEvent]:
    """Point-in-time event view: future local receipts are invisible regardless of venue time."""
    if engine_local_ns <= 0:
        raise ValueError("engine_local_ns must be positive")
    return [event for event in deterministic_event_order(events)
            if event.local_ingestion_ns <= engine_local_ns]
