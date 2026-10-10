import pytest

from execution.adaptive_pacing import PaceAction, choose_pace


def base(**overrides):
    values = dict(
        side="buy", ofi=0.5, microprice_edge_bps=0.2, spread_bps=1.0,
        market_age_seconds=0.1, passive_order_live=False,
    )
    values.update(overrides)
    return choose_pace(**values)


def test_aligned_ofi_accelerates():
    result = base()
    assert result.action == PaceAction.ACCELERATE
    assert result.interval_multiplier == 0.5


def test_opposed_ofi_slows():
    result = base(ofi=-0.5)
    assert result.action == PaceAction.SLOW
    assert result.interval_multiplier == 2.0


def test_adverse_microprice_withdraws_passive_order():
    result = base(microprice_edge_bps=-1.0, passive_order_live=True)
    assert result.action == PaceAction.WITHDRAW_PASSIVE


def test_stale_feed_halts_execution_recommendation():
    result = base(market_age_seconds=2.1)
    assert result.action == PaceAction.HALT_STALE


def test_sell_side_alignment_is_inverted():
    result = base(side="sell", ofi=-0.6)
    assert result.action == PaceAction.ACCELERATE


def test_bad_ofi_rejected():
    with pytest.raises(ValueError):
        base(ofi=1.5)
