from execution.twap_ledger import TwapLedger, evaluate_chase


def test_one_btc_parent_slices_into_ten_children_over_two_hours(tmp_path):
    with TwapLedger(tmp_path / "twap.sqlite") as ledger:
        children = ledger.create_parent("parent-1", 1.0, child_count=10, start_ms=0, duration_ms=7_200_000)
        assert len(children) == 10
        assert all(abs(c.quantity - 0.1) < 1e-12 for c in children)
        assert [c.due_ms for c in children] == [i * 720_000 for i in range(10)]
        assert abs(sum(c.quantity for c in children) - 1.0) < 1e-12


def test_parent_creation_is_idempotent_across_retries(tmp_path):
    path = tmp_path / "twap.sqlite"
    with TwapLedger(path) as ledger:
        first = ledger.create_parent("parent-1", 1.0, start_ms=0)
        second = ledger.create_parent("parent-1", 1.0, start_ms=0)
        assert [x.client_order_id for x in first] == [x.client_order_id for x in second]
        assert len(second) == 10
        try:
            ledger.create_parent("parent-1", 2.0, start_ms=0)
        except ValueError:
            pass
        else:
            raise AssertionError("reusing parent ID with changed parameters must fail")


def test_restart_recovers_child_state_without_duplicate_parent(tmp_path):
    path = tmp_path / "twap.sqlite"
    with TwapLedger(path) as ledger:
        ledger.create_parent("parent-1", 1.0, start_ms=0)
        due = ledger.due_child("parent-1", 0)
        assert due is not None
        ledger.mark_submitting(due.client_order_id)
    with TwapLedger(path) as restarted:
        assert len(restarted.children("parent-1")) == 10
        unknown = restarted.reconcile("parent-1", [])
        assert unknown["needs_fill_history_reconciliation"] == ["parent-1:0001"]
        assert restarted.children("parent-1")[0].state == "UNKNOWN"
        assert restarted.due_child("parent-1", 0) is None


def test_open_exchange_order_is_reconciled_by_stable_client_id(tmp_path):
    with TwapLedger(tmp_path / "twap.sqlite") as ledger:
        ledger.create_parent("parent-1", 1.0, start_ms=0)
        due = ledger.due_child("parent-1", 0)
        ledger.mark_submitting(due.client_order_id)
        result = ledger.reconcile("parent-1", [due.client_order_id])
        assert result["matched_open"] == [due.client_order_id]
        assert result["needs_fill_history_reconciliation"] == []


def test_child_cannot_be_dispatched_twice(tmp_path):
    with TwapLedger(tmp_path / "twap.sqlite") as ledger:
        ledger.create_parent("parent-1", 1.0, start_ms=0)
        child = ledger.due_child("parent-1", 0)
        ledger.mark_submitting(child.client_order_id)
        try:
            ledger.mark_submitting(child.client_order_id)
        except ValueError:
            pass
        else:
            raise AssertionError("duplicate dispatch must be rejected")


def test_chase_within_three_ticks_reprices_passively():
    decision = evaluate_chase(side="buy", passive_price=100.0, best_bid=103.0, best_ask=104.0, tick_size=1.0)
    assert decision.action == "REPRICE_PASSIVE"
    assert decision.chase_ticks == 3
    assert decision.target_price < 104.0


def test_chase_beyond_three_ticks_waits_until_next_interval():
    decision = evaluate_chase(side="buy", passive_price=100.0, best_bid=104.0, best_ask=105.0, tick_size=1.0)
    assert decision.action == "WAIT_NEXT_INTERVAL"
    assert decision.reason == "CHASE_LIMIT_BREACHED"
    assert decision.target_price is None


def test_sell_chase_stays_passive():
    decision = evaluate_chase(side="sell", passive_price=110.0, best_bid=105.0, best_ask=106.0, tick_size=1.0)
    assert decision.action == "WAIT_NEXT_INTERVAL"


def test_acknowledged_child_missing_from_open_orders_requires_history_lookup(tmp_path):
    with TwapLedger(tmp_path / "twap.sqlite") as ledger:
        ledger.create_parent("parent-1", 1.0, start_ms=0)
        child = ledger.due_child("parent-1", 0)
        ledger.mark_submitting(child.client_order_id)
        ledger.record_ack(child.client_order_id, "exchange-123")
        result = ledger.reconcile("parent-1", [])
        assert result["needs_fill_history_reconciliation"] == [child.client_order_id]
        assert ledger.children("parent-1")[0].state == "UNKNOWN"


def test_chase_distance_of_3_49_ticks_is_rejected_not_rounded_down():
    decision = evaluate_chase(side="buy", passive_price=100.0, best_bid=103.49, best_ask=104.0, tick_size=1.0)
    assert decision.action == "REJECT"
    assert decision.reason == "PRICE_OFF_TICK_GRID"


def test_next_child_waits_for_prior_child_result_and_does_not_burst_after_pause(tmp_path):
    with TwapLedger(tmp_path / "twap.sqlite") as ledger:
        children = ledger.create_parent("parent-1", 1.0, start_ms=0)
        first = ledger.due_child("parent-1", 0)
        ledger.mark_submitting(first.client_order_id)
        assert ledger.due_child("parent-1", 7_200_000) is None
        ledger.record_ack(first.client_order_id, "exchange-1")
        assert ledger.due_child("parent-1", 7_200_000) is None
        ledger.record_result(first.client_order_id, state="FILLED", filled_quantity=first.quantity)
        next_child = ledger.due_child("parent-1", 7_200_000)
        assert next_child is not None
        assert next_child.ordinal == 2
        assert next_child.due_ms == 720_000


def test_parent_completion_is_derived_from_all_authoritative_child_fills(tmp_path):
    with TwapLedger(tmp_path / "twap.sqlite") as ledger:
        children = ledger.create_parent("parent-1", 1.0, start_ms=0)
        assert ledger.refresh_parent_state("parent-1")["state"] == "ACTIVE"
        for child in children:
            ledger.mark_submitting(child.client_order_id)
            ledger.record_ack(child.client_order_id, f"exchange-{child.ordinal}")
            ledger.record_result(child.client_order_id, state="FILLED", filled_quantity=child.quantity)
        summary = ledger.refresh_parent_state("parent-1")
        assert summary["state"] == "COMPLETE"
        assert abs(summary["filled_quantity"] - 1.0) < 1e-12
        assert summary["remaining_quantity"] == 0.0
