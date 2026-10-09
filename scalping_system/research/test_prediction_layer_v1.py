from pathlib import Path
import sys
import math

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research.prediction_layer_v1 import build_rows, walk_forward


def candles(n=220):
    # Deterministic fixture, used only to test indexing and leakage controls.
    return [{"timestamp": 1_700_000_000 + i * 60, "open": 100 + i,
             "high": 101 + i, "low": 99 + i, "close": 100 + i,
             "volume": 10 + i % 7} for i in range(n)]


def test_features_use_only_asof_micro_and_labels_are_future_close():
    cs = candles(70)
    micro = [{"ts": cs[20]["timestamp"] + 60, "mid": 1000,
              "imb5": 0.4, "delta30": 0.2, "spread_bps": 1, "ret30": 0.01},
             {"ts": cs[20]["timestamp"] + 61, "imb5": -0.9, "delta30": -1}]
    rows = build_rows(cs, micro, horizons={"h": 1}, max_micro_age_seconds=2)
    assert rows[20]["features"]["micro_imb5"] == 0.4
    assert math.isnan(rows[21]["features"]["micro_imb5"])
    assert rows[20]["labels"]["h"]["future_close"] == cs[21]["close"]
    assert rows[20]["labels"]["h"]["future_ts"] == cs[21]["timestamp"] + 60
    assert rows[-1]["labels"] == {}


def test_walk_forward_is_ordered_and_applies_purge_and_embargo():
    rows = build_rows(candles(220), horizons={"h": 3})
    result = walk_forward(rows, "h", folds=3, min_train=90, embargo_bars=2)
    assert result["status"] == "RESEARCH_ONLY"
    assert result["purge_bars"] == 3
    assert result["embargo_bars"] == 2
    assert len(result["folds"]) == 3
    for fold in result["folds"]:
        assert fold["train_n"] > 0
        assert fold["train_end_ts"] < fold["test_start_ts"]
        assert fold["test_n"] > 0
    assert result["auto_apply"] is False
    assert result["real_orders"] is False


def test_short_history_fails_closed_as_insufficient():
    rows = build_rows(candles(20), horizons={"h": 1})
    result = walk_forward(rows, "h", min_train=30)
    assert result["status"] == "INSUFFICIENT_DATA"
