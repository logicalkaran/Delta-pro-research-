"""V3.1 research layer: pressure-vs-capacity and liquidity-state filters.
Does not modify frozen Fisher or submit orders.
"""
from dataclasses import dataclass
from strategy.timezone_gate import gate as timezone_gate

@dataclass(frozen=True)
class V31Config:
    min_trades_5: int = 4
    max_spread_bps: float = 5.0
    max_fresh: float = 2.0
    min_delta5: float = .12
    min_delta30: float = .08
    min_imb: float = .12
    min_mom: float = .025
    min_expected: float = .12
    cost_buffer: float = .05
    min_capacity_ratio: float = .002
    max_fragility: float = .70

def _f(x,d=0):
    try: return float(x)
    except: return d

def evaluate(state,cfg=V31Config()):
    tg=timezone_gate(state.get("timestamp"))
    if not tg["allowed"]:
        return {"action":"NO_TRADE","reason":tg["reason"],"session":tg["session"],"utc_hour":tg["utc_hour"]}
    w5=state["windows"]["5"]; w30=state["windows"]["30"]; ob=state["order_book"]; q=state["quality"]
    mid=_f(ob.get("mid_price")); spread=_f(ob.get("spread")); fresh=_f(q.get("fresh_seconds"),999)
    if mid<=0 or fresh>cfg.max_fresh or w5["trades"]<cfg.min_trades_5:
        return {"action":"NO_TRADE","reason":"QUALITY_BLOCK"}
    spread_bps=spread/mid*10000
    if spread_bps>cfg.max_spread_bps:
        return {"action":"NO_TRADE","reason":"SPREAD_BLOCK"}
    d5=_f(w5.get("delta_pct")); d30=_f(w30.get("delta_pct")); imb=_f(ob.get("imbalance_5")); mom=_f(state["price"]["5"]["return_pct"])
    bd=max(_f(ob.get("bid_depth_5")),1e-9); ad=max(_f(ob.get("ask_depth_5")),1e-9)
    pressure_buy=abs(_f(w5.get("buy_volume")))/ad
    pressure_sell=abs(_f(w5.get("sell_volume")))/bd
    depth_total=bd+ad
    fragility=min(1.0,(spread_bps/cfg.max_spread_bps)*.5 + (1/(1+depth_total))*1e5*.5)
    long_align=d5>=cfg.min_delta5 and d30>=cfg.min_delta30 and imb>=cfg.min_imb and mom>=cfg.min_mom
    short_align=d5<=-cfg.min_delta5 and d30<=-cfg.min_delta30 and imb<=-cfg.min_imb and mom<=-cfg.min_mom
    expected=abs(mom)+abs(d5)*.15+abs(imb)*.10
    if expected<cfg.min_expected+cfg.cost_buffer:
        return {"action":"NO_TRADE","reason":"EDGE_TOO_SMALL","expected":expected}
    if fragility>cfg.max_fragility:
        return {"action":"NO_TRADE","reason":"LIQUIDITY_FRAGILITY","fragility":fragility}
    if long_align and pressure_buy>=cfg.min_capacity_ratio:
        return {"action":"LONG","confidence":min(.99,.5+expected*.4),"expected_move_pct":expected,"pressure_capacity":pressure_buy,"fragility":fragility,"reason":"ALIGNMENT+CAPACITY"}
    if short_align and pressure_sell>=cfg.min_capacity_ratio:
        return {"action":"SHORT","confidence":min(.99,.5+expected*.4),"expected_move_pct":expected,"pressure_capacity":pressure_sell,"fragility":fragility,"reason":"ALIGNMENT+CAPACITY"}
    return {"action":"NO_TRADE","reason":"ALIGNMENT_BLOCK","pressure_capacity":pressure_buy if d5>0 else pressure_sell,"fragility":fragility}
