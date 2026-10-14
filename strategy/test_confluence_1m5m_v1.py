from strategy.confluence_1m5m_v1 import evaluate, ConfluenceConfig
import time


def candles(n, start, drift):
    out=[]; p=start
    for i in range(n):
        q=p+drift
        out.append({"timestamp":i,"open":p,"high":max(p,q)+0.8,"low":min(p,q)-0.2,"close":q,"volume":100+i%9})
        p=q
    return out


def state(side="LONG"):
    bullish=side=="LONG"
    px=10000.0
    return {"updated_at_epoch":time.time(),"symbol":"BTCUSD","regime":"BUYER_ABSORPTION" if bullish else "SELLER_ABSORPTION",
        "quality":{"fresh_seconds":0.1,"book_samples":100},
        "windows":{"5":{"delta_pct":0.8 if bullish else -0.8},"30":{"delta_pct":0.6 if bullish else -0.6}},
        "cvd_slope_30s":2 if bullish else -2,
        "order_book":{"mid_price":px,"best_bid":px-0.5,"best_ask":px+0.5,
            "bid_depth_5":2000 if bullish else 500,"ask_depth_5":500 if bullish else 2000,
            "imbalance_5":0.6 if bullish else -0.6}}


def test_stale_data_abstains():
    s=state(); s["quality"]["fresh_seconds"]=10
    d=evaluate(candles(100,10000,2),candles(60,9900,5),s)
    assert d["decision"]=="NO_TRADE" and d["reason"]=="STALE_MARKET_DATA"


def test_wide_spread_abstains():
    s=state(); s["order_book"]["best_ask"]=s["order_book"]["mid_price"]+10
    d=evaluate(candles(100,10000,2),candles(60,9900,5),s)
    assert not d["allowed"] and "SPREAD_TOO_WIDE" in d["rejected"]


def test_missing_history_abstains():
    d=evaluate(candles(20,10000,2),candles(10,9900,5),state())
    assert d["decision"]=="NO_TRADE" and "INSUFFICIENT_1M_HISTORY" in d["rejected"]


def test_decisions_never_enable_live_orders():
    d=evaluate(candles(100,10000,2),candles(60,9900,5),state())
    assert d["paper_only"] and d["real_orders"] is False and d["live_execution_enabled"] is False


def test_1_to_1_plan_when_decision_is_returned():
    d=evaluate(candles(100,10000,2),candles(60,9900,5),state(),ConfluenceConfig(round_trip_cost_bps=0.1,min_expected_net_bps=0.0,min_move_to_cost_multiple=0.0))
    assert d["reward_to_risk"]==1.0
    if d["allowed"]:
        assert abs(abs(d["target"]-d["entry_reference"])-abs(d["entry_reference"]-d["stop"]))<1e-6
