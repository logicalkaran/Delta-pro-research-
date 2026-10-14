from decimal import Decimal as D
from paper.async_simulation_adapter import AsyncSimulationAdapter
from execution.async_order_simulator import OrderState, EIGHT_HOURS_MS


def test_adapter_is_explicitly_research_only_and_delays_order_ack():
    a=AsyncSimulationAdapter(latency_ms=5)
    a.update_book({'100':'2'},{'101':'2'},0)
    o=a.submit_intent('buy','100','1',0)
    assert o.state==OrderState.SUBMITTING
    a.execution.advance(5)
    assert o.state==OrderState.ACKNOWLEDGED
    assert a.snapshot()['live_orders_enabled'] is False
    assert a.snapshot()['mode']=='RESEARCH_SIMULATION_ONLY'


def test_adapter_funding_uses_boundary_mark_price():
    a=AsyncSimulationAdapter()
    a.ledger.set_position('2','100')
    a.ledger.set_funding_rate('0.001',0)
    assert a.settle_funding(EIGHT_HOURS_MS, boundary_rate='0.001', mark_price='110')[0]['payment']=='-0.220'
