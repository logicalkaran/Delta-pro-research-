import math
import pytest
from research.event_features import BookEvent, mlofi
from research.queue_simulator import PassiveQueue
from research.adverse_selection import post_fill_markout, volume_weighted_markout, evaluate_expected_value
from research.model_evaluator import murphy_brier_decomposition

def book(ts, bid_qty=10, ask_qty=10, bid=100, ask=101):
    bids=[[bid-i, bid_qty if i==0 else 5] for i in range(5)]
    asks=[[ask+i, ask_qty if i==0 else 5] for i in range(5)]
    return BookEvent.from_levels(ts,bids,asks)

def test_mlofi_mutation_and_weights():
    r=mlofi(book(1),book(2,bid_qty=12),decay=.5)
    assert r["clock_kind"]=="exchange_event_time" and r["changed"] and r["mlofi"]>0
    assert len(r["bid_ofi_levels"])==5 and r["weights"][0]==1 and r["weights"][1]<1

def test_mlofi_rejects_duplicate_time_and_unchanged_book():
    a=book(1)
    with pytest.raises(ValueError): mlofi(a,book(2))
    with pytest.raises(ValueError): mlofi(a,book(1,bid_qty=11))
    with pytest.raises(ValueError): BookEvent.from_levels(float("nan"),[[1,1]]*5,[[2,1]]*5)

def test_mlofi_validates_depth_and_crossed_book():
    with pytest.raises(ValueError): BookEvent.from_levels(1,[[100,1]],[[101,1]])
    with pytest.raises(ValueError): BookEvent.from_levels(1,[[102-i,1] for i in range(5)],[[101+i,1] for i in range(5)])

def test_queue_fill_uses_correct_aggressor():
    q=PassiveQueue(side="buy",queue_ahead=5,limit_price=100,placed_ts=1)
    assert not q.on_event(event_ts=2,aggressive_buy_volume=50).filled
    r=q.on_event(event_ts=3,aggressive_sell_volume=5)
    assert r.filled and r.fill_ts==3 and r.remaining_queue==0

def test_queue_cancels_when_not_consumed_and_rejects_reversal():
    q=PassiveQueue(side="sell",queue_ahead=10,limit_price=101,placed_ts=1)
    with pytest.raises(ValueError): q.on_event(event_ts=1,aggressive_buy_volume=1)
    q.on_event(event_ts=2,aggressive_sell_volume=100)
    assert q.expire(now_ts=3).status=="CANCELED"

def test_queue_thinning_uses_displayed_volume_reference():
    q=PassiveQueue(side="buy",queue_ahead=50,limit_price=100,placed_ts=1,displayed_queue_volume=100)
    q.on_event(event_ts=2,displayed_queue_volume=80)
    assert q.remaining_queue==pytest.approx(40.0)

def test_markout_sign_and_weighted_aggregation():
    buy=post_fill_markout(side="buy",fill_price=100,future_mid=99,observed_volume=2)
    sell=post_fill_markout(side="sell",fill_price=100,future_mid=99,observed_volume=1)
    assert buy["markout_bps"]<0 and buy["adverse_selection_bps"]>0 and sell["markout_bps"]>0
    assert volume_weighted_markout([buy,sell])["volume_weighted_markout_bps"]<0

def test_ev_gate_explicitly_applies_assumed_fees():
    assert evaluate_expected_value(gross_edge_bps=4)["net_expected_value_bps"]==1
    assert not evaluate_expected_value(gross_edge_bps=2)["approved_for_research"]
    assert evaluate_expected_value(gross_edge_bps=4)["fee_assumptions_verified"] is False
    with pytest.raises(ValueError): evaluate_expected_value(gross_edge_bps=1,taker_fee_bps=-1)

def test_murphy_decomposition_reconstructs_binned_not_raw_brier():
    r=murphy_brier_decomposition([.1,.2,.8,.9],[0,0,1,1],bins=5)
    assert r["n"]==4 and 0<=r["brier_score"]<=1 and r["resolution"]>0
    assert abs(r["binned_brier_score"]-r["decomposed_brier"])<1e-12
    assert r["decomposition_residual"]==pytest.approx(0)
    assert r["raw_vs_binned_gap"]>=0

def test_murphy_rejects_invalid_inputs():
    with pytest.raises(ValueError): murphy_brier_decomposition([],[])
    with pytest.raises(ValueError): murphy_brier_decomposition([1.1],[1])
    with pytest.raises(ValueError): murphy_brier_decomposition([.5],[2])
