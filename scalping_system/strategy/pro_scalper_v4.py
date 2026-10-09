"""Professional Scalper V4 research engine. PAPER ONLY.
Combines flow, book pressure, price response/absorption, forecast and execution economics.
No exchange order submission.
"""
def f(x,d=0.0):
    try:return float(x)
    except:return d

def cost_model(notional_usd, taker_fee_bps=5.9, spread_bps=0.5, slippage_bps=1.0, safety_bps=2.0):
    # Conservative Delta India BTCUSD assumption: 0.05% taker per side + 18% GST on fees = 5.9 bps/side.
    fees=2*taker_fee_bps
    return {"fees_bps":fees,"spread_bps":spread_bps,"slippage_bps":slippage_bps,
            "safety_bps":safety_bps,"total_cost_bps":fees+spread_bps+slippage_bps+safety_bps}

def evaluate(state, forecast=None):
    w=state.get("windows",{}); ob=state.get("order_book",{}); p=state.get("price",{})
    d5=f(w.get("5",{}).get("delta_pct")); d30=f(w.get("30",{}).get("delta_pct")); d60=f(w.get("60",{}).get("delta_pct"))
    imb=f(ob.get("imbalance_5")); spread=f(ob.get("spread")); mid=f(ob.get("mid_price"))
    cvd=f(state.get("cvd_slope_30s")); mom=f(p.get("5",{}).get("return_pct"))
    buy=f(w.get("30",{}).get("buy_volume")); sell=f(w.get("30",{}).get("sell_volume"))
    flow_abs=abs(buy-sell)
    ret30=f(p.get("30",{}).get("return_pct"))
    # Pressure-to-price response: large flow with tiny price movement suggests absorption.
    response_bps=abs(ret30)*100
    absorption_score=min(1.0, flow_abs/max(1.0,buy+sell))
    absorption=(absorption_score>0.20 and response_bps<0.04)
    score=0
    if d5>0.08: score+=2
    elif d5<-0.08: score-=2
    if d30>0.08: score+=2
    elif d30<-0.08: score-=2
    if imb>0.12: score+=2
    elif imb<-0.12: score-=2
    if cvd>0: score+=1
    elif cvd<0: score-=1
    if mom>0.025: score+=1
    elif mom<-0.025: score-=1
    # Strong pressure with failure to move: fade the pressure.
    if absorption:
        if sell>buy: score+=2
        elif buy>sell: score-=2
    base="LONG" if score>=5 else "SHORT" if score<=-5 else "NO_TRADE"
    if forecast:
        fd=forecast.get("horizon_30s",{}).get("direction")
        if base=="LONG" and fd!="UP": base="NO_TRADE"
        if base=="SHORT" and fd!="DOWN": base="NO_TRADE"
    spread_bps=spread/max(mid,1e-9)*10000
    veto=[]
    fresh=f(state.get("quality",{}).get("fresh_seconds"),999)
    if fresh>2:veto.append("STALE_DATA")
    if spread_bps>5:veto.append("WIDE_SPREAD")
    if absorption and base=="NO_TRADE": veto.append("ABSORPTION_UNRESOLVED")
    # Minimum predicted move needed to overcome taker economics.
    expected_move_bps=max(0.0,abs(score)*3.0)
    costs=cost_model(0,spread_bps=spread_bps)
    net_edge=expected_move_bps-costs["total_cost_bps"]
    if net_edge<=2.0: veto.append("INSUFFICIENT_NET_EDGE")
    if veto: action="NO_TRADE"
    else: action=base
    return {"action":action,"base_signal":base,"score":score,
            "expected_move_bps":round(expected_move_bps,3),
            "net_edge_bps":round(net_edge,3),
            "costs":costs,
            "absorption":absorption,"response_bps":round(response_bps,4),
            "spread_bps":round(spread_bps,3),"vetoes":veto,
            "paper_only":True,"order_submission":False}
