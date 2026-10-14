from research.orderflow_absorption_features_v1 import OrderFlowAbsorptionTape


def test_sell_pressure_with_stable_price_flags_possible_buyer_absorption():
    tape = OrderFlowAbsorptionTape()
    for t, p in [(1, 100), (10, 100.001), (20, 100.002)]:
        tape.add_book(t, p, 100, 90)
    tape.add_trade(5, 100, 100, "sell")
    tape.add_trade(15, 100, 80, "sell")
    f = tape.features(now=20)
    assert f.status == "OK"
    assert f.cvd_delta == -180
    assert f.cvd_divergence == "POSSIBLE_BUYER_ABSORPTION"
    assert "NOT_PROOF" in f.caveat


def test_depth_replenishment_ratio_detects_bid_recovery():
    tape = OrderFlowAbsorptionTape()
    for t, bid in [(1, 100), (5, 40), (10, 75)]:
        tape.add_book(t, 100, bid, 100)
    tape.add_trade(9, 100, 1, "buy")
    f = tape.features(now=10)
    assert f.bid_replenishment_ratio == 0.5833


def test_stale_book_fails_closed():
    tape = OrderFlowAbsorptionTape(max_book_age_seconds=2)
    tape.add_book(1, 100, 10, 10)
    tape.add_trade(1, 100, 1, "sell")
    assert tape.features(now=10).status == "INSUFFICIENT_OR_STALE_DATA"


def test_bounded_buffers_and_invalid_inputs():
    tape = OrderFlowAbsorptionTape(max_trades=2, max_books=2)
    assert not tape.add_trade(1, 0, 1, "sell")
    for t in range(1, 5):
        tape.add_trade(t, 100, 1, "buy")
        tape.add_book(t, 100, 10, 10)
    assert len(tape.trades) == 2
    assert len(tape.books) == 2
