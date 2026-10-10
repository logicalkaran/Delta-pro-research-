from research.queue_depletion_replay_v1 import replay


def event(t, message):
    return {"receive_epoch_ns": int((1_800_000_000 + t) * 1_000_000_000), "message": message}


def l2(t, bid="100", bq="5", ask="102", aq="5"):
    return event(t, {"type": "ob_l2", "b": [[bid, bq], ["99", "10"]], "a": [[ask, aq], ["103", "10"]]})


def l1(t, bid="100", bq="5", ask="102", aq="5"):
    return event(t, {"type": "ob_l1", "bp": bid, "bs": bq, "ap": ask, "as": aq})


def trade(t, price="100", size="3", side="m"):
    return event(t, {"type": "trades", "p": price, "s": size, "r": side})


def test_fill_requires_queue_ahead_plus_our_order_size_and_marks_out():
    records = [l2(0), trade(0.2, size="3"), trade(0.3, size="3")]
    records += [l1(1.31), l1(5.31), l1(15.31), l1(30.31), l1(60.31)]
    result = replay(records, order_size=__import__("decimal").Decimal("1"))
    assert result["counts"]["orders_placed"] == 1
    assert result["fill_count"] == 1
    fill = result["fills"][0]
    assert fill["fill_reason"] == "QUEUE_DEPLETION"
    assert fill["sell_volume_at_limit"] == 6.0
    assert all(fill["markouts_bps"][str(h)] is not None for h in (1, 5, 15, 30, 60))


def test_ambiguous_exact_tier_flow_requires_price_through_fallback():
    records = [l2(0), trade(0.2, size="1", side="?")]
    records += [l1(0.3, bid="99.5", bq="5", ask="100", aq="3")]
    result = replay(records)
    assert result["fill_count"] == 1
    assert result["fills"][0]["fill_reason"] == "PRICE_THROUGH_AMBIGUOUS_TRADE_FLOW"
    assert result["counts"]["ambiguous_exact_tier_trades"] == 1


def test_adverse_microprice_cancels_as_missed_fill_not_loss():
    records = [l2(0, bq="1", aq="100"), l1(0.1, bid="100", bq="1", ask="102", aq="100")]
    result = replay(records)
    assert result["fill_count"] == 0
    assert result["missed_fill_count"] == 1
    assert result["missed_fills"][0]["status"] == "MISSED_FILL"
    assert result["counts"]["adverse_momentum_misses"] == 1


def test_microprice_reversion_cancels_theoretical_bid():
    records = [l2(0, bq="100", aq="1"), l1(0.1, bid="100", bq="1", ask="102", aq="100")]
    result = replay(records)
    assert result["fill_count"] == 0
    assert result["counts"]["microprice_reversion_cancels"] == 1
    assert result["missed_fills"][0]["reason"] == "MICROPRICE_REVERTED_BELOW_MID"


def test_displayed_queue_growth_cancels_as_conservative_proxy():
    records = [l2(0, bq="5", aq="5"), l2(0.1, bq="6", aq="5")]
    result = replay(records)
    assert result["fill_count"] == 0
    assert result["counts"]["queue_front_running_cancels"] == 1
    assert result["missed_fills"][0]["reason"] == "DISPLAYED_QUEUE_SIZE_INCREASE_PROXY"
