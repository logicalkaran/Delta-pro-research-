from research.quant_protocol_aligned_capture_v1 import extract_snapshot

def valid_state():
    return {"symbol":"BTCUSD","updated_at_epoch":1000.0,
      "order_book":{"mid_price":100.0,"best_bid":99.5,"best_ask":100.5,
        "imbalance_5":0.2,"bids_l5":[[99.5,2],[99,3]],"asks_l5":[[100.5,1],[101,4]]},
      "windows":{"30":{"delta_pct":0.4},"1":{"buy_volume":10,"sell_volume":4}},
      "quality":{"fresh_seconds":0.1,"trade_samples":100,"book_samples":50},
      "price":{"last":100},"last_trade":{"price":100}}

def test_extract_snapshot_preserves_aligned_flow_and_l5():
    r=extract_snapshot(valid_state(),"s",1,1000.1)
    assert r["quality_status"]=="PASS"
    assert r["delta30"]==0.4 and r["imb5"]==0.2
    assert r["signed_flow_1s"]==6
    assert r["bids_l5"][0]==[99.5,2.0]
    assert r["timestamp_kind"]=="local_state_refresh_not_exchange_book_event"

def test_extract_snapshot_fails_closed_on_stale_or_missing_book():
    s=valid_state(); s["quality"]["fresh_seconds"]=4
    assert "STALE_OR_UNKNOWN_SOURCE_AGE" in extract_snapshot(s,"s",1)["quality_reasons"]
    s=valid_state(); s["order_book"]["bids_l5"]=[]
    assert "MISSING_L5_LEVELS" in extract_snapshot(s,"s",1)["quality_reasons"]

def test_invalid_numbers_are_rejected_not_serialized_as_nan():
    s=valid_state(); s["order_book"]["mid_price"]=float("nan")
    r=extract_snapshot(s,"s",1)
    assert r["quality_status"]=="REJECT"
    assert "INVALID_TOP_OF_BOOK" in r["quality_reasons"]
