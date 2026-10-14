import importlib.util
from pathlib import Path
P=Path(__file__).with_name('ofi_l2_tape_v2.py')
S=importlib.util.spec_from_file_location('ofi_tape',P); M=importlib.util.module_from_spec(S); S.loader.exec_module(M)

def test_bid_volume_increase_is_positive_ofi():
    prev={'bids_l5':[[100,5]],'asks_l5':[[101,4]]}
    cur={'bids_l5':[[101,7]],'asks_l5':[[101,4]]}
    assert M.ofi(prev,cur)['ofi_l5']==7

def test_equal_price_uses_volume_delta():
    prev={'bids_l5':[[100,5]],'asks_l5':[[101,4]]}
    cur={'bids_l5':[[100,8]],'asks_l5':[[101,6]]}
    assert M.ofi(prev,cur)['ofi_l5']==1

def test_ask_price_falling_is_supply_delta_then_subtracted():
    prev={'bids_l5':[[100,5]],'asks_l5':[[102,4]]}
    cur={'bids_l5':[[100,5]],'asks_l5':[[101,6]]}
    assert M.ofi(prev,cur)['ofi_l5']==-6


def test_snapshot_does_not_fabricate_missing_timestamp():
    r=M.snapshot({"order_book":{"mid_price":100,"best_bid":99.5,"best_ask":100.5,
                               "bids_l5":[[99.5,2]],"asks_l5":[[100.5,3]]},
                  "quality":{"fresh_seconds":0.1,"book_samples":1}}, "test")
    assert r["ts"] is None
    assert r["timestamp_valid"] is False
    assert r["source_event_timestamp_present"] is False
    assert r["timestamp_kind"] == "local_state_refresh_not_exchange_book_event"


def test_snapshot_marks_invalid_freshness_instead_of_defaulting_fresh():
    r=M.snapshot({"updated_at_epoch":123.0,
                  "order_book":{"mid_price":100,"best_bid":99.5,"best_ask":100.5,
                               "bids_l5":[[99.5,2]],"asks_l5":[[100.5,3]]},
                  "quality":{}}, "test")
    assert r["source_age_valid"] is False
    assert r["source_fresh_seconds"] is None


def test_snapshot_does_not_fabricate_missing_timestamp():
    r=M.snapshot({"order_book":{"mid_price":100,"best_bid":99.5,"best_ask":100.5,
                               "bids_l5":[[99.5,2]],"asks_l5":[[100.5,3]]},
                  "quality":{"fresh_seconds":0.1,"book_samples":1}}, "test")
    assert r["ts"] is None
    assert r["timestamp_valid"] is False
    assert r["source_event_timestamp_present"] is False
    assert r["timestamp_kind"] == "local_state_refresh_not_exchange_book_event"


def test_snapshot_marks_invalid_freshness_instead_of_defaulting_fresh():
    r=M.snapshot({"updated_at_epoch":123.0,
                  "order_book":{"mid_price":100,"best_bid":99.5,"best_ask":100.5,
                               "bids_l5":[[99.5,2]],"asks_l5":[[100.5,3]]},
                  "quality":{}}, "test")
    assert r["source_age_valid"] is False
    assert r["source_fresh_seconds"] is None
