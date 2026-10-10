from decimal import Decimal as D
import random

import pytest

from execution.paper_simulator import PaperSimulator
from storage.event_journal import EventJournal


def make_sim(tmp_path, *, seed=1, latency=(100, 400)):
    journal = EventJournal(tmp_path / "events.sqlite")
    sim = PaperSimulator(journal, initial_equity="1000", rng=random.Random(seed), clock_ms=lambda: 10_000,
                         min_latency_ms=latency[0], max_latency_ms=latency[1])
    sim.update_book(bid="99", ask="100", mark="99.5", bid_size="0.5", ask_size="0.4", timestamp_ms=9_900)
    sim.create_parent("p1", "1", now_ms=10_000)
    return journal, sim


def test_marketable_buy_partial_fill_and_taker_fee_accounting(tmp_path):
    journal, sim = make_sim(tmp_path, seed=1, latency=(100, 100))
    try:
        order = sim.submit_limit(client_order_id="p1:1", parent_id="p1", side="buy", limit_price="100", quantity="1", now_ms=10_000)
        assert order.state == "DISPATCHED"
        assert order.ack_due_ms == 10_100
        sim.advance(now_ms=10_100)
        assert order.filled_quantity == D("0.4")
        assert order.remaining == D("0.6")
        assert order.state == "PARTIAL_FILL"
        assert sim.cash == D("1000") - D("40") - D("0.02")
        events = [x["event_type"] for x in journal.replay()]
        assert "CHILD_DISPATCHED" in events and "CHILD_ACKNOWLEDGED" in events
        assert "CHILD_PARTIAL_FILL" in events and "PAPER_FEE" in events
    finally:
        journal.close()


def test_marketable_sell_fills_at_bid_and_charges_taker_fee(tmp_path):
    journal, sim = make_sim(tmp_path, latency=(100, 100))
    try:
        order = sim.submit_limit(client_order_id="p1:short", parent_id="p1", side="sell", limit_price="99", quantity="0.2", now_ms=10_000)
        sim.advance(now_ms=10_100)
        assert order.state == "FILLED"
        assert order.average_fill_price == D("99")
        assert sim.cash == D("1000") + D("19.8") - D("0.0099")
        assert sim.position_qty == D("-0.2")
    finally:
        journal.close()


def test_passive_order_waits_for_explicit_trade_evidence_and_gets_rebate(tmp_path):
    journal, sim = make_sim(tmp_path, latency=(100, 100))
    try:
        order = sim.submit_limit(client_order_id="p1:maker", parent_id="p1", side="buy", limit_price="99", quantity="0.1", now_ms=10_000)
        sim.advance(now_ms=10_100)
        assert order.state == "RESTING"
        assert order.filled_quantity == 0
        sim.on_trade(price="99", quantity="0.1", aggressor_side="sell", now_ms=10_200)
        assert order.state == "FILLED"
        assert sim.cash == D("1000") - D("9.9") + D("0.00198")
        assert any(x["event_type"] == "PAPER_REBATE" for x in journal.replay())
    finally:
        journal.close()


def test_client_id_is_idempotent_and_parameter_mismatch_rejected(tmp_path):
    journal, sim = make_sim(tmp_path)
    try:
        first = sim.submit_limit(client_order_id="p1:idempotent", parent_id="p1", side="buy", limit_price="99", quantity="0.1", now_ms=10_000)
        again = sim.submit_limit(client_order_id="p1:idempotent", parent_id="p1", side="buy", limit_price="99", quantity="0.1", now_ms=10_000)
        assert first is again
        assert sum(e["event_type"] == "CHILD_DISPATCHED" for e in journal.replay()) == 1
        with pytest.raises(ValueError, match="different order parameters"):
            sim.submit_limit(client_order_id="p1:idempotent", parent_id="p1", side="buy", limit_price="98", quantity="0.1", now_ms=10_000)
    finally:
        journal.close()


def test_stale_and_crossed_books_fail_closed(tmp_path):
    journal = EventJournal(tmp_path / "events.sqlite")
    sim = PaperSimulator(journal, clock_ms=lambda: 10_000)
    try:
        with pytest.raises(ValueError, match="crossed or locked"):
            sim.update_book(bid="100", ask="100", mark="100", bid_size="1", ask_size="1", timestamp_ms=10_000)
        sim.update_book(bid="99", ask="100", mark="99.5", bid_size="1", ask_size="1", timestamp_ms=1)
        with pytest.raises(RuntimeError, match="stale"):
            sim.submit_limit(client_order_id="p:1", parent_id="p", side="buy", limit_price="99", quantity="0.1", now_ms=10_000)
    finally:
        journal.close()


def test_latency_is_deterministic_and_inside_configured_range(tmp_path):
    journal, sim = make_sim(tmp_path, seed=42, latency=(100, 400))
    try:
        order = sim.submit_limit(client_order_id="p1:latency", parent_id="p1", side="buy", limit_price="99", quantity="0.1", now_ms=10_000)
        latency = order.ack_due_ms - 10_000
        assert 100 <= latency <= 400
        assert latency == random.Random(42).randint(100, 400)
    finally:
        journal.close()


def test_book_timestamp_must_be_nonnegative_and_finite_prices_required(tmp_path):
    journal = EventJournal(tmp_path / "events.sqlite")
    sim = PaperSimulator(journal, clock_ms=lambda: 10_000)
    try:
        with pytest.raises(ValueError):
            sim.update_book(bid="nan", ask="100", mark="99", bid_size="1", ask_size="1", timestamp_ms=1)
        with pytest.raises(ValueError):
            sim.update_book(bid="99", ask="100", mark="99", bid_size="1", ask_size="1", timestamp_ms=-1)
    finally:
        journal.close()


def test_restart_restores_child_and_same_client_id_does_not_redispatch(tmp_path):
    journal, sim = make_sim(tmp_path, latency=(100, 100))
    try:
        original = sim.submit_limit(client_order_id="p1:restart", parent_id="p1", side="buy",
                                    limit_price="99", quantity="0.1", now_ms=10_000)
        restored = PaperSimulator(journal, initial_equity="1000", rng=random.Random(1),
                                  clock_ms=lambda: 10_000, min_latency_ms=100, max_latency_ms=100)
        again = restored.submit_limit(client_order_id="p1:restart", parent_id="p1", side="buy",
                                      limit_price="99", quantity="0.1", now_ms=10_000)
        assert again.ack_due_ms == original.ack_due_ms
        assert again.state == "DISPATCHED"
        assert sum(e["event_type"] == "CHILD_DISPATCHED" for e in journal.replay()) == 1
    finally:
        journal.close()
