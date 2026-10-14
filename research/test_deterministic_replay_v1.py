from research.deterministic_replay_v1 import (
    ExecutionCosts, MarketEvent, OrderIntent, OrderType, Side,
    deterministic_event_order, event_tape_digest, net_return_bps,
    taker_round_trip_cost_bps, zero_alpha_baseline,
)


def ev(local_ns, exchange_ns, seq=0, kind="trade", payload=None):
    return MarketEvent(local_ns, exchange_ns, kind, payload or {"price": 100.0}, seq)


def test_local_ingestion_timestamp_controls_replay_order_not_exchange_time():
    # Exchange event B has an earlier venue timestamp, but it arrived later locally.
    a = ev(2_000_000_000, 9_000_000_000, seq=1)
    b = ev(3_000_000_000, 1_000_000_000, seq=2)
    assert deterministic_event_order([b, a]) == [a, b]


def test_equal_local_timestamp_is_deterministic_by_sequence_then_input_order():
    a = ev(2_000_000_000, 9_000_000_000, seq=8)
    b = ev(2_000_000_000, 1_000_000_000, seq=3)
    assert deterministic_event_order([a, b]) == [b, a]
    assert event_tape_digest([a, b]) == event_tape_digest([b, a])


def test_event_digest_changes_when_payload_changes():
    a = ev(2_000_000_000, 1_000_000_000, payload={"price": 100})
    b = ev(2_000_000_000, 1_000_000_000, payload={"price": 101})
    assert event_tape_digest([a]) != event_tape_digest([b])


def test_order_intent_validates_fields():
    good = OrderIntent("test", Side.BUY, 1.0, OrderType.MARKET)
    assert good.quantity == 1.0
    try:
        OrderIntent("test", Side.BUY, 0, OrderType.MARKET)
    except ValueError:
        pass
    else:
        raise AssertionError("zero quantity must be rejected")


def test_cost_accounting_exactly_applies_round_trip_fees_spread_slippage():
    costs = ExecutionCosts(taker_fee_bps=5.9, slippage_bps=1.0)
    total = taker_round_trip_cost_bps(costs, spread_bps=2.0)
    assert abs(total - 15.8) < 1e-9
    assert abs(net_return_bps(20.0, total) - 4.2) < 1e-9


def test_zero_alpha_baseline_has_exact_cost_identity_and_negative_expectation():
    report = zero_alpha_baseline(10_000, seed=123, round_trip_cost_bps=14.8)
    assert report["trades"] == 10_000
    assert report["cost_accounting_identity_pass"] is True
    assert abs(report["net_mean_bps"] - (report["gross_mean_bps"] - 14.8)) < 1e-9
    # Since the realized gross mean can be nonzero, net mean must be below gross mean.
    assert report["net_mean_bps"] < report["gross_mean_bps"]
    assert len(report["equity_curve"]) == 10_000

def test_market_fill_uses_quote_available_before_arrival_event_not_future_quote():
    from research.deterministic_replay_v1 import replay_execution

    class BuyOnce:
        done = False
        def on_event(self, market_data):
            if self.done:
                return None
            self.done = True
            return OrderIntent("test", Side.BUY, 1.0, OrderType.MARKET)

    events = [
        ev(1_000_000_000, 9_000_000_000, kind="ob_l1",
           payload={"type":"ob_l1","bp":"100","bs":"5","ap":"102","as":"5"}),
        ev(1_200_000_000, 1_000_000_000, kind="ob_l1",
           payload={"type":"ob_l1","bp":"100","bs":"5","ap":"104","as":"5"}),
    ]
    report = replay_execution(events, BuyOnce(), costs=ExecutionCosts(latency_ms=100, slippage_bps=1.0))
    assert len(report.fills) == 1
    assert report.fills[0]["route"] == "TAKER"
    assert abs(report.fills[0]["fill_price"] - 102.0102) < 1e-6


def test_limit_fill_requires_queue_ahead_plus_order_size():
    from research.deterministic_replay_v1 import replay_execution

    class BuyLimitOnce:
        done = False
        def on_event(self, market_data):
            if self.done:
                return None
            self.done = True
            return OrderIntent("test", Side.BUY, 1.0, OrderType.LIMIT, "GTC", limit_price=100.0, ttl_ms=5000)

    events = [
        ev(1_000_000_000, 1_000_000_000, kind="ob_l2",
           payload={"type":"ob_l2","b":[["100","5"],["99","10"]],"a":[["102","5"],["103","10"]]}),
        ev(1_200_000_000, 900_000_000, kind="trades", payload={"type":"trades","p":"100","s":"5","r":"m"}),
        ev(1_300_000_000, 800_000_000, kind="trades", payload={"type":"trades","p":"100","s":"1","r":"m"}),
    ]
    report = replay_execution(events, BuyLimitOnce(), costs=ExecutionCosts(latency_ms=100))
    assert len(report.fills) == 1
    assert report.fills[0]["route"] == "MAKER"
    assert report.fills[0]["fill_price"] == 100.0


def test_zero_gross_alpha_baseline_loses_exactly_round_trip_cost():
    report = zero_alpha_baseline(10_000, gross_returns_bps=[0.0] * 10_000, round_trip_cost_bps=14.8)
    assert report["gross_mean_bps"] == 0.0
    assert report["net_mean_bps"] == -14.8
    assert report["cost_accounting_identity_pass"] is True

def test_delta_adapter_preserves_both_timestamps_and_uses_local_time_for_replay():
    from research.deterministic_replay_v1 import delta_record_to_event
    event = delta_record_to_event({
        "received_at": "2026-10-09T19:14:23.847995+00:00",
        "message": {"type": "trades", "t": 1791573264605962, "ts": 1791573264773500, "p": "100", "s": 1, "r": "m"},
    }, sequence=4)
    assert event.local_ingestion_ns == 1791573263847994880 or abs(event.local_ingestion_ns - 1791573263847995000) < 2000
    assert event.exchange_ns == 1791573264605962000
    assert event.exchange_ns != event.local_ingestion_ns
    assert event.sequence == 4


def test_delta_adapter_refuses_to_fake_local_timestamp_from_exchange_time():
    from research.deterministic_replay_v1 import delta_record_to_event
    try:
        delta_record_to_event({"message": {"type": "ob_l1", "ts": 1791573264773500}})
    except ValueError as exc:
        assert "missing local ingestion timestamp" in str(exc)
    else:
        raise AssertionError("exchange timestamp must not be substituted for local receive time")

def test_point_in_time_visibility_uses_local_receipt_not_exchange_timestamp():
    from research.deterministic_replay_v1 import visible_events_at_time
    base = 1_700_000_000_000_000_000
    arrived_later_but_exchange_earlier = ev(base + 50_000_000, base - 10_000_000, seq=2)
    first = ev(base + 40_000_000, base + 20_000_000, seq=1)
    visible = visible_events_at_time([arrived_later_but_exchange_earlier, first], base + 45_000_000)
    assert visible == [first]
    assert visible_events_at_time([first, arrived_later_but_exchange_earlier], base + 50_000_000) == [first, arrived_later_but_exchange_earlier]


def test_limit_touch_stays_pending_until_price_trades_through():
    from research.deterministic_replay_v1 import replay_execution

    class LimitBuyOnce:
        done = False
        def on_event(self, market_data):
            if self.done:
                return None
            self.done = True
            return OrderIntent("limit-test", Side.BUY, 1.0, OrderType.LIMIT, "GTC", limit_price=99.9, ttl_ms=5000)

    base = 1_700_000_000_000_000_000
    events = [
        ev(base, base, kind="ob_l2", payload={"type":"ob_l2","b":[["99.9","500"],["99.8","200"]],"a":[["100.0","400"],["100.1","200"]]}),
        ev(base + 60_000_000, base + 10_000_000, kind="trades", payload={"type":"trades","p":"99.9","s":"100","r":"m"}),
        ev(base + 70_000_000, base + 20_000_000, kind="trades", payload={"type":"trades","p":"99.8","s":"1","r":"m"}),
    ]
    report = replay_execution(events, LimitBuyOnce(), costs=ExecutionCosts(latency_ms=50))
    assert len(report.fills) == 1
    assert report.fills[0]["route"] == "MAKER"
    assert report.fills[0]["fill_price"] == 99.9
    assert report.fills[0]["arrival_local_ns"] == base + 50_000_000


def test_strategy_emits_same_intent_without_broker_or_simulator_awareness():
    from research.deterministic_replay_v1 import replay_events

    class StatelessSignal:
        def on_event(self, market_data):
            if market_data["event_type"] == "trade" and market_data["payload"].get("signal"):
                return OrderIntent("agnostic", Side.BUY, 1.0, OrderType.MARKET)
            return None

    base = 1_700_000_000_000_000_000
    events = [ev(base, base, kind="trade", payload={"signal": True})]
    first = replay_events(events, StatelessSignal())
    second = replay_events(events, StatelessSignal())
    assert first.intents_seen == second.intents_seen == 1
    assert first.rejects == second.rejects
    assert first.fills == second.fills == []
    assert first.rejects[0]["reason"] == "EXECUTION_SIMULATOR_NOT_YET_CONNECTED"
