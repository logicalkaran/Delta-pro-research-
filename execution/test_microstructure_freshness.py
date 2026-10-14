from execution.live_perpetual_controller import signal
from delta_collector import microstructure


def signal_state(*, trade_age=0.1, price_age=0.1, book_age=0.1, include_ages=True):
    quality = {"fresh_seconds": 0.1}
    if include_ages:
        quality.update({
            "trade_fresh_seconds": trade_age,
            "price_fresh_seconds": price_age,
            "book_fresh_seconds": book_age,
        })
    return {
        "windows": {
            "5": {"trades": 5, "delta_pct": 0.20},
            "30": {"trades": 12, "delta_pct": 0.10},
        },
        "order_book": {"imbalance_5": 0.20},
        "price": {"5": {"return_pct": 0.04}},
        "quality": quality,
    }


def test_signal_fails_closed_if_stream_ages_missing():
    assert signal(signal_state(include_ages=False)) is None


def test_fresh_aggregate_cannot_mask_stale_trade_stream():
    assert signal(signal_state(trade_age=3.0)) is None


def test_stale_price_or_book_stream_rejects_signal():
    assert signal(signal_state(price_age=2.1)) is None
    assert signal(signal_state(book_age=2.1)) is None


def test_signal_allowed_only_when_each_input_stream_is_fresh():
    assert signal(signal_state()) == "LONG"


def test_state_exposes_independent_receive_ages(monkeypatch):
    now = 1_800_000_000.0
    monkeypatch.setattr(microstructure.time, "time", lambda: now)
    monkeypatch.setattr(microstructure, "_last_update", now - 0.1)
    monkeypatch.setattr(microstructure, "_last_trade_update", now - 0.2)
    monkeypatch.setattr(microstructure, "_last_price_update", now - 0.3)
    monkeypatch.setattr(microstructure, "_last_l1_update", now - 0.4)
    monkeypatch.setattr(microstructure, "_last_l2_update", now - 3.0)
    monkeypatch.setattr(microstructure, "_book", {
        "bids": {100.0: 1.0}, "asks": {101.0: 1.0}, "ts": 1_799_999_997_000_000
    })
    state = microstructure._state()
    assert state["quality"]["trade_fresh_seconds"] == 0.2
    assert state["quality"]["price_fresh_seconds"] == 0.3
    assert state["quality"]["book_fresh_seconds"] == 3.0
