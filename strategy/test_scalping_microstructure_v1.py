from strategy.scalping_microstructure_v1 import (
    estimate_queue, microprice, imbalance_persistence, execution_quality
)


def book():
    return {
        "bids": {100.0: 4.0, 99.9: 2.0},
        "asks": {100.2: 1.0, 100.3: 3.0},
        "best_bid": 100.0,
        "best_ask": 100.2,
        "tick_size": 0.1,
    }


def test_queue_price_time_proxy():
    q = estimate_queue(book(), side="BUY", limit_price=100.0, own_size=1.0)
    assert q.available
    assert q.queue_ahead == 4.0
    assert 0.79 < q.queue_fraction < 0.81


def test_microprice_moves_toward_heavier_bid():
    b = book()
    b["bids"] = {100.0: 9.0}
    b["asks"] = {100.2: 1.0}
    m = microprice(b)
    assert m.valid
    assert m.microprice > m.mid
    assert m.directional_bias > 0


def test_imbalance_persistence_and_flip():
    p = imbalance_persistence([-0.3, -0.2, 0.25, 0.35], side="LONG")
    assert p.valid
    assert p.flip
    assert p.aligned_fraction == 0.5
    assert p.persistence > 0


def test_execution_quality_penalizes_adverse_passive_entry():
    b = book()
    b["bids"] = {100.0: 1.0}
    b["asks"] = {100.2: 9.0}
    m = microprice(b)
    q = estimate_queue(b, side="BUY", limit_price=100.0, own_size=1.0)
    e = execution_quality(
        b, side="LONG", limit_price=100.0, order_size=1.0,
        predicted_move_bps=2.0, queue=q, micro=m
    )
    assert e.adverse_selection_bps > 0
    assert not e.executable
