import random
from research.pro_scalper_v5 import evaluate
from research.pro_scalper_v5_costs import calculate, round_tick, funding_crossings
from paper.pro_scalper_v5_paper import PaperEngine
from research.pro_scalper_v5_evaluator import deduplicate, split, evaluate as evaluate_rows

def state():
    return {"updated_at_epoch":1000,"regime":"TEST","quality":{"fresh_seconds":.2,"trade_samples":8},
      "order_book":{"best_bid":99999.5,"best_ask":100000,"mid_price":99999.75,"imbalance_5":.7,"imbalance_10":.5},
      "windows":{"5":{"delta_pct":.8,"trades":8},"30":{"delta_pct":.7},"60":{"delta_pct":.5}},
      "price":{"5":{"return_pct":.04},"30":{"return_pct":.08},"60":{"return_pct":.1}},"cvd_slope_30s":3}

def test_fee_gst_and_no_double_count():
    x=calculate(1000,20,"MAKER","TAKER")
    assert x.fees_bps==2.36+5.90
    assert x.fees_usd==pytest_approx(0.826)
    assert x.net_bps==20-(2.36+5.90)

def pytest_approx(x):
    # Avoid an optional dependency in the mobile test environment.
    return type("Approx",(),{"__eq__":lambda self,y:abs(y-x)<1e-9})()

def test_tick_rounding_conservative():
    assert round_tick(100.74,side="BUY")==100.5
    assert round_tick(100.74,side="SELL")==101.0

def test_stale_data_abstains():
    s=state(); s["quality"]["fresh_seconds"]=9
    assert evaluate(s,now_ts=1000)["action"]=="ABSTAIN"

def test_score_never_reads_future_target():
    s=state(); s["target"]={"future_return":999999,"net_bps":100000}
    a=evaluate(s,now_ts=1000)
    del s["target"]
    assert a==evaluate(s,now_ts=1000)
    assert a["score_is_probability"] is False

def test_maker_fill_uncertainty_and_cost_floor():
    cfg={"paper_notional_usd":100,"min_score":4,"max_fresh_seconds":2,"max_spread_bps":4,"min_samples_5s":3,
         "paper_target_bps":100,"min_net_edge_bps":0,"maker_fill_probability":0.5,"maker_queue_fraction":0,
         "max_hold_seconds":90}
    missed=PaperEngine(cfg,rng=random.Random(0))
    r=missed.step(state(),now_ts=1000)
    assert r["position"] is None and r["reason"]=="MAKER_MISSED_OR_QUEUED"
    filled=PaperEngine(cfg,rng=random.Random(1))
    r=filled.step(state(),now_ts=1000)
    assert r["position"] and r["position"]["entry_kind"]=="MAKER"
    assert r["real_orders"] is False

def test_funding_settlement_boundaries():
    assert funding_crossings(1,28800)==[28800]
    assert funding_crossings(28800,28801)==[]

def test_evaluator_dedup_chronology_and_embargo():
    rows=[{"ts":3},{"ts":1},{"ts":2},{"ts":2},{"ts":4}]
    assert [r["ts"] for r in deduplicate(rows)]==[1,2,3,4]
    left,right=split(rows,embargo_seconds=0)
    assert max(r["ts"] for r in left)<min(r["ts"] for r in right)
    left,right=split(rows,embargo_seconds=1)
    assert [r["ts"] for r in left]==[1] and [r["ts"] for r in right]==[4]

def test_evaluator_reports_separate_walkforward_halves_without_feature_leakage():
    rows=[{"ts":i,"features":{"signal":1},"target":{"net_bps":2,"gross_bps":10},"side":"LONG","regime":"R"} for i in range(10)]
    report=evaluate_rows(rows,embargo_seconds=1)
    assert report["train_metrics"]["sample_count"]>0
    assert report["test_metrics"]["sample_count"]>0
    assert report["future_labels_used_as_features"] is False
    assert report["metrics"]["net_expectancy_bps"]==2
