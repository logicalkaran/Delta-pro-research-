from opportunity_regime_discovery_v1 import discover, state
import json

import live_microstructure_feature_tape_v1 as feature_tape


def row(ts, move=4.0):
    return {
        "ts": ts, "spread_bps": 0.1, "imb5": 0.3, "delta5": 0.8,
        "delta30": 0.1, "ret5": 0.1, "ret30": 0.2, "ret60": 0.01,
        "labels": {h: {"future_ts": ts + int(h), "move_bps": move} for h in ("60", "120", "180", "300")},
    }


def test_state_uses_only_present_features_and_has_requested_axes():
    s = state(row(1))
    assert len(s) == 7
    assert s[0] == "low_vol"
    assert s[2] == "bid_heavy"


def test_feature_tape_preserves_source_percent_points(tmp_path, monkeypatch):
    source = {
        "price": {"5": {"return_pct": 0.1}, "30": {"return_pct": -0.2},
                  "60": {"return_pct": 0.04}},
    }
    path = tmp_path / "state.json"
    path.write_text(json.dumps(source))
    monkeypatch.setattr(feature_tape, "STATE", path)

    features = feature_tape.snapshot()

    assert features["ret5"] == 0.1
    assert features["ret30"] == -0.2
    assert features["ret60"] == 0.04
    assert state({**features, "imb5": 0, "delta5": 0, "delta30": 0})[0] == "high_vol"


def test_state_converts_percent_points_before_volatility_and_price_axes():
    low = row(1)
    assert state(low)[0] == "low_vol"  # 0.01 percentage points = 1 bp
    assert state(low)[-1] == "trend"

    high = {**low, "ret5": -0.1, "ret30": 0.2, "ret60": 0.031,
            "delta5": 0.8, "delta30": -0.4}
    result = state(high)
    assert result[0] == "high_vol"  # 0.031 percentage points exceeds 3 bps
    assert result[3] == "buy_accel"
    assert result[4] == "flow_price_divergence"
    assert result[5] == "toxic_flow"
    assert result[6] == "mean_reversion"


def test_discovery_costs_metrics_and_research_only_status():
    report = discover([row(i * 400) for i in range(30)])
    assert report["status"] == "research_only"
    assert report["cohorts_evaluated"] > 0
    result = report["results"][0]
    assert result["direction"] == "long"
    assert result["n"] == 30
    assert result["avg_net_bps"] < 4.0
    assert len(result["purged_chronological_folds"]) == 4
    assert "stable_positive" in result["half_split"]
