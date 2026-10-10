from decimal import Decimal as D
import pytest
from execution.async_order_simulator import AsyncOrderSimulator, OrderState, PerpetualLedger, EIGHT_HOURS_MS


def test_latency_and_queue_snapshot_at_ack():
    s=AsyncOrderSimulator(20); s.update_book({'100':'7'},{'101':'2'},0)
    o=s.submit('buy','100','2',1)
    assert o.state==OrderState.SUBMITTING
    s.advance(20); assert o.state==OrderState.SUBMITTING
    s.advance(21); assert o.state==OrderState.ACKNOWLEDGED and o.queue_ahead==7


def test_queue_depletion_supports_partial_fills():
    s=AsyncOrderSimulator(0); s.update_book({'100':'5'},{'101':'2'},0)
    o=s.submit('buy','100','3',0); s.advance(0)
    s.trade('100','7','sell',1)
    assert o.state==OrderState.PARTIAL_FILL and o.filled_quantity==2 and o.queue_ahead==0
    s.trade('100','1','sell',2)
    assert o.state==OrderState.FILLED and o.filled_quantity==3 and s.inventory==3


def test_fill_wins_race_while_cancel_is_in_transit():
    s=AsyncOrderSimulator(10); s.update_book({'100':'0'},{'101':'1'},0)
    o=s.submit('buy','100','1',0); s.advance(10); s.cancel(o.order_id,11)
    assert o.state==OrderState.CANCEL_PENDING
    s.trade('100','1','sell',15); assert o.state==OrderState.FILLED
    s.advance(21)
    assert o.state==OrderState.CANCEL_REJECTED and s.inventory==1


def test_mark_price_drives_pnl_and_liquidation():
    l=PerpetualLedger(cash=D('1')); l.set_position('1','100')
    assert D(l.margin_snapshot('99')['unrealized_pnl'])==-1
    result=l.check_liquidation('90')
    assert result['liquidated'] and l.position_qty==0 and D(result['liquidation_penalty'])>0


def test_funding_settles_only_at_eight_hour_boundary():
    l=PerpetualLedger(); l.set_position('2','100'); l.set_funding_rate('0.001',0)
    assert l.settle_through(EIGHT_HOURS_MS-1)==[] and l.realized_funding==0
    rows=l.settle_through(EIGHT_HOURS_MS)
    assert len(rows)==1 and D(rows[0]['payment'])==D('-0.2') and l.realized_funding==D('-0.2')


def test_invalid_inputs_are_rejected():
    with pytest.raises(ValueError): AsyncOrderSimulator(-1)
    s=AsyncOrderSimulator(); s.advance(10)
    with pytest.raises(ValueError): s.advance(9)
    with pytest.raises(ValueError): s.submit('buy','0','1',10)
