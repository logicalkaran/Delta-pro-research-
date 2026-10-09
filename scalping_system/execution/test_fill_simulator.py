import pytest
from execution.fill_simulator import FillModel, simulate

def test_maker_can_miss():
    r = simulate(20, "MAKER", rng_value=1.0)
    assert not r.filled

def test_maker_costs_include_adverse_selection():
    r = simulate(20, "MAKER", FillModel(adverse_selection_bps=2), rng_value=0.0)
    assert r.filled
    assert r.total_cost_bps > 0
    assert r.net_edge_bps < 20

def test_taker_is_always_filled_but_expensive():
    r = simulate(20, "TAKER", rng_value=0.0)
    assert r.filled
    assert r.total_cost_bps >= 2 * 5.90
    assert r.net_edge_bps < 20
