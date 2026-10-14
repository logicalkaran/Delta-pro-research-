from strategy.scalping_features_v1 import (
    atr,
    book_imbalance,
    compute_cvd,
    detect_fvg,
    detect_sweep,
    zscore,
)


def candle(o, h, l, c, v=100):
    return {"open": o, "high": h, "low": l, "close": c, "volume": v}


def test_low_sweep_uses_prior_window_only():
    rows = [candle(100, 101, 99, 100) for _ in range(20)]
    rows.append(candle(100, 101, 98, 100.5))
    s = detect_sweep(rows, lookback=20)
    assert s.direction == "LOW_SWEEP"
    assert s.level == 99
    assert s.depth == 1
    assert s.rejection > 0


def test_high_sweep():
    rows = [candle(100, 101, 99, 100) for _ in range(20)]
    rows.append(candle(100, 102, 99, 99.5))
    s = detect_sweep(rows, lookback=20)
    assert s.direction == "HIGH_SWEEP"
    assert s.level == 101


def test_bullish_fvg():
    rows = [
        candle(100, 101, 99, 100),
        candle(100, 105, 100, 104),
        candle(104, 108, 103, 107),
    ]
    f = detect_fvg(rows)
    assert f.direction == "BULLISH"
    assert f.low == 101
    assert f.high == 103
    assert f.midpoint == 102
    assert f.size == 2


def test_bearish_fvg():
    rows = [
        candle(105, 110, 104, 109),
        candle(109, 109, 100, 101),
        candle(100, 103, 98, 99),
    ]
    f = detect_fvg(rows)
    assert f.direction == "BEARISH"
    assert f.low == 103
    assert f.high == 104


def test_cvd():
    trades = [
        {"price": 100, "size": 2, "side": "buy"},
        {"price": 100, "size": 1, "side": "sell"},
        {"price": 100, "size": 3, "role": "t"},
        {"price": 100, "size": 2, "role": "m"},
    ]
    c = compute_cvd(trades, prior_cvd=10)
    assert c.buy_volume == 5
    assert c.sell_volume == 3
    assert c.delta == 2
    assert c.cumulative == 12
    assert round(c.delta_ratio, 6) == round(2 / 8, 6)


def test_book_imbalance_from_existing_live_schema():
    b = {
        "best_bid": 100.0,
        "best_ask": 100.5,
        "bid_depth_5": 120.0,
        "ask_depth_5": 80.0,
    }
    x = book_imbalance(b, levels=5)
    assert x.imbalance == 0.2
    assert round(x.spread_bps, 6) == round(0.5 / 100.25 * 10000, 6)


def test_book_imbalance_from_raw_levels():
    b = {
        "bids": {100: 10, 99.5: 20},
        "asks": {100.5: 5, 101: 5},
    }
    x = book_imbalance(b, levels=2)
    assert x.bid_depth == 30
    assert x.ask_depth == 10
    assert x.imbalance == 0.5


def test_zscore_requires_history():
    assert zscore(10, [10] * 10) == 0.0
    assert zscore(12, list(range(20))) > 0
