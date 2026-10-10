from research.raw_archive_feature_tape_v1 import stream_feature_rows


def event(t, message):
    return {"receive_epoch_ns": int((1_800_000_000 + t) * 1_000_000_000), "message": message}


def test_feature_tape_streams_book_rows_and_one_second_signed_flow():
    records = [
        event(0.0, {"type": "trades", "p": "100", "s": "2", "r": "m", "sy": "BTCUSD"}),
        event(0.2, {"type": "ob_l2", "b": [["100", "5"], ["99", "3"]], "a": [["101", "2"], ["102", "4"]], "sy": "BTCUSD"}),
        event(0.4, {"type": "trades", "p": "100", "s": "1", "r": "t", "sy": "BTCUSD"}),
        event(1.5, {"type": "ob_l1", "bp": "100", "bs": "5", "ap": "101", "as": "2", "sy": "BTCUSD"}),
    ]
    rows = list(stream_feature_rows(records, "s1"))
    assert len(rows) == 2
    assert rows[0]["session_id"] == "s1"
    assert rows[0]["signed_trade_flow_1s"] == -2.0
    assert rows[0]["microprice_status"] == "OK"
    assert rows[1]["signed_trade_flow_1s"] == 0.0


def test_delta_bid_replenishment_rate_uses_same_venue_contract_units():
    records = [
        event(0.0, {"type": "ob_l2", "b": [["100", "5"], ["99", "3"]], "a": [["101", "2"], ["102", "4"]], "sy": "BTCUSD"}),
        event(0.1, {"type": "trades", "p": "100", "s": "3", "r": "m", "sy": "BTCUSD"}),
        event(0.31, {"type": "ob_l2", "b": [["100", "6"], ["99", "3"]], "a": [["101", "2"], ["102", "4"]], "sy": "BTCUSD"}),
    ]
    rows = list(stream_feature_rows(records, "s1"))
    assert rows[-1]["delta_bid_replenishment_status"] == "OK"
    assert abs(rows[-1]["delta_bid_replenishment_rate_200ms"] - (4 / 3)) < 1e-9
    assert abs(rows[-1]["delta_bid_replenishment_window_ms"] - 210.0) < 1e-3


def test_negative_replenishment_vetoes_bullish_microprice_candidate():
    records = [
        event(0.0, {"type": "ob_l2", "b": [["100", "5"], ["99", "3"]], "a": [["101", "2"], ["102", "4"]], "sy": "BTCUSD"}),
        event(0.1, {"type": "trades", "p": "100", "s": "3", "r": "m", "sy": "BTCUSD"}),
        event(0.31, {"type": "ob_l2", "b": [["100", "1"], ["99", "3"]], "a": [["101", "0.1"], ["102", "0.2"]], "sy": "BTCUSD"}),
    ]
    rows = list(stream_feature_rows(records, "s1"))
    assert rows[-1]["delta_bid_replenishment_rate_200ms"] < 0
    assert rows[-1]["microprice_bullish_replenishment_gate"] == "VETO"
