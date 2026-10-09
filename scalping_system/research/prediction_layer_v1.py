"""Leakage-safe, research-only BTC prediction dataset and walk-forward evaluator.

This module does not connect to execution or strategy code. Candle timestamps are
treated as bar-open UTC seconds; features become available at bar close. Optional
microstructure rows are joined only when timestamped at/before that close.
Future labels use close-to-close returns. Results are diagnostics, not signals.
"""
from __future__ import annotations

import json
import math
import statistics
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
CANDLES = ROOT / "data/live_candles.json"
MICRO = ROOT / "data/processed/live_microstructure_features_v1.jsonl"
OUT = ROOT / "data/processed/prediction_layer_v1.json"
HORIZONS = {"scalp_1m": 1, "scalp_5m": 5, "intraday_15m": 15, "swing_1h": 60}
FEATURES = ("ret_1m", "ret_5m", "ret_15m", "ret_1h", "trend_5m", "trend_15m",
            "trend_1h", "volatility_15m", "volume_z_15m", "micro_imb5",
            "micro_delta30", "micro_spread_bps", "micro_ret30")
# Explicit round-trip research assumptions, expressed in basis points. Replace
# only with venue/fee data verified for the intended instrument/account.
DEFAULT_COSTS = {"taker_fee_roundtrip_bps": 10.0, "slippage_roundtrip_bps": 2.0,
                 "extra_spread_roundtrip_bps": 2.0}


def _num(value: Any, default: float = math.nan) -> float:
    try:
        x = float(value)
        return x if math.isfinite(x) else default
    except (TypeError, ValueError):
        return default


def _mean(xs: list[float]) -> float:
    return statistics.fmean(xs) if xs else math.nan


def _std(xs: list[float]) -> float:
    return statistics.pstdev(xs) if len(xs) > 1 else math.nan


def _ret(a: float, b: float) -> float:
    return b / a - 1.0 if a > 0 and b > 0 else math.nan


def build_rows(candles: Iterable[dict], micro: Iterable[dict] = (),
               horizons: dict[str, int] = HORIZONS,
               max_micro_age_seconds: float = 2.0) -> list[dict]:
    """Build causal features and future labels from sorted 1m candles.

    Context windows represent closed bars ending at the current row. Micro rows
    are as-of joined to candle close, never to a later observation.
    """
    cs = sorted((dict(x) for x in candles), key=lambda x: _num(x.get("timestamp")))
    ms = sorted((dict(x) for x in micro), key=lambda x: _num(x.get("ts")))
    if any(_num(c.get("close")) <= 0 or not math.isfinite(_num(c.get("timestamp"))) for c in cs):
        raise ValueError("candles require finite timestamps and positive closes")
    closes = [_num(c["close"]) for c in cs]
    volumes = [_num(c.get("volume"), 0.0) for c in cs]
    out = []
    mi = 0
    latest_micro = None
    for i, c in enumerate(cs):
        close_ts = _num(c["timestamp"]) + 60.0
        while mi < len(ms) and _num(ms[mi].get("ts")) <= close_ts:
            latest_micro = ms[mi]
            mi += 1
        def window_return(n: int) -> float:
            return _ret(closes[i-n], closes[i]) if i >= n else math.nan
        def trend(n: int) -> float:
            if i < n: return math.nan
            return _mean(closes[i-n+1:i+1]) / _mean(closes[i-2*n+1:i-n+1]) - 1 if i >= 2*n-1 else math.nan
        vwin = volumes[max(0, i-14):i+1]
        vm, vs = _mean(vwin), _std(vwin)
        v_z = (volumes[i]-vm)/vs if math.isfinite(vs) and vs > 0 else math.nan
        age = close_ts - _num(latest_micro.get("ts")) if latest_micro else math.inf
        fresh = latest_micro is not None and 0 <= age <= max_micro_age_seconds
        row = {"ts": close_ts, "close": closes[i], "features": {
            "ret_1m": window_return(1), "ret_5m": window_return(5),
            "ret_15m": window_return(15), "ret_1h": window_return(60),
            "trend_5m": trend(5), "trend_15m": trend(15), "trend_1h": trend(60),
            "volatility_15m": _std([_ret(closes[j-1], closes[j]) for j in range(max(1, i-14), i+1)]),
            "volume_z_15m": v_z,
            "micro_imb5": _num(latest_micro.get("imb5")) if fresh else math.nan,
            "micro_delta30": _num(latest_micro.get("delta30")) if fresh else math.nan,
            "micro_spread_bps": _num(latest_micro.get("spread_bps")) if fresh else math.nan,
            "micro_ret30": _num(latest_micro.get("ret30")) if fresh else math.nan,
        }, "micro_age_seconds": age if math.isfinite(age) else None}
        labels = {}
        for name, bars in horizons.items():
            j = i + int(bars)
            if bars > 0 and j < len(cs):
                gross = _ret(closes[i], closes[j]) * 10000
                labels[name] = {"future_ts": _num(cs[j]["timestamp"]) + 60.0,
                                "future_close": closes[j], "gross_return_bps": gross}
        row["labels"] = labels
        out.append(row)
    return out


def hypothesis_scores(rows: list[dict], label: str, costs: dict[str, float] = DEFAULT_COSTS) -> dict:
    """Evaluate small, predeclared directional hypotheses; no fitted thresholds."""
    fixed_cost = (float(costs.get("taker_fee_roundtrip_bps", 0.0))
                  + float(costs.get("slippage_roundtrip_bps", 0.0)))
    spread_floor = float(costs.get("extra_spread_roundtrip_bps", 0.0))
    definitions = {
        "multi_tf_trend_continuation": lambda f: 1 if all(_num(f.get(k), 0) > 0 for k in ("trend_5m", "trend_15m")) else (-1 if all(_num(f.get(k), 0) < 0 for k in ("trend_5m", "trend_15m")) else 0),
        "microstructure_confirmed_1m_momentum": lambda f: 1 if _num(f.get("ret_1m"), 0) > 0 and _num(f.get("micro_imb5"), 0) > 0 and _num(f.get("micro_delta30"), 0) > 0 else (-1 if _num(f.get("ret_1m"), 0) < 0 and _num(f.get("micro_imb5"), 0) < 0 and _num(f.get("micro_delta30"), 0) < 0 else 0),
        "higher_tf_pullback": lambda f: 1 if _num(f.get("trend_15m"), 0) > 0 and _num(f.get("ret_1m"), 0) < 0 else (-1 if _num(f.get("trend_15m"), 0) < 0 and _num(f.get("ret_1m"), 0) > 0 else 0),
    }
    result = {}
    for name, fn in definitions.items():
        net = [fn(r["features"]) * _num(r.get("labels", {}).get(label, {}).get("gross_return_bps"))
               - fixed_cost - max(spread_floor, _num(r["features"].get("micro_spread_bps"), 0.0))
               for r in rows if label in r.get("labels", {}) and fn(r["features"]) != 0]
        net = [x for x in net if math.isfinite(x)]
        result[name] = {"n": len(net), "coverage": len(net) / max(1, sum(label in r.get("labels", {}) for r in rows)),
                        "mean_net_bps": _mean(net) if net else None,
                        "win_rate": sum(x > 0 for x in net) / len(net) if net else None}
    return result


def walk_forward(rows: list[dict], label: str, folds: int = 3,
                 min_train: int = 120, embargo_bars: int | None = None,
                 costs: dict[str, float] = DEFAULT_COSTS) -> dict:
    """Expanding chronological folds. Purge outcome overlap and embargo test start."""
    if folds < 1: raise ValueError("folds must be positive")
    horizon = HORIZONS.get(label)
    if horizon is None:
        # Derive the forward span for custom labels from timestamp spacing.
        spans = []
        for r in rows:
            target = r.get("labels", {}).get(label, {}).get("future_ts")
            if target is not None:
                spans.append(_num(target) - _num(r.get("ts")))
                if len(spans) >= 20: break
        steps = [_num(rows[i+1].get("ts")) - _num(rows[i].get("ts"))
                 for i in range(min(len(rows)-1, 100))]
        step = statistics.median([x for x in steps if x > 0]) if any(x > 0 for x in steps) else 60.0
        horizon = max(1, int(round(statistics.median(spans) / step))) if spans else 1
    embargo = horizon if embargo_bars is None else max(0, int(embargo_bars))
    eligible = [i for i, r in enumerate(rows) if label in r.get("labels", {})]
    first_test_pos = min_train + horizon + embargo
    if len(eligible) < first_test_pos + folds:
        return {"status": "INSUFFICIENT_DATA", "n_labeled": len(eligible), "folds": [],
                "min_train": min_train, "purge_bars": horizon, "embargo_bars": embargo}
    test_size = max(1, (len(eligible) - first_test_pos) // folds)
    out = []
    for k in range(folds):
        test_start_pos = first_test_pos + k * test_size
        test_end_pos = len(eligible) if k == folds-1 else min(len(eligible), test_start_pos + test_size)
        test_idx = eligible[test_start_pos:test_end_pos]
        if not test_idx: continue
        first_test = test_idx[0]
        # Training labels must mature before the embargoed test region begins.
        train_cutoff = first_test - embargo - horizon
        train_idx = [i for i in eligible[:test_start_pos] if i < train_cutoff]
        test_rows = [rows[i] for i in test_idx]
        scores = hypothesis_scores(test_rows, label, costs)
        out.append({"fold": k+1, "train_n": len(train_idx), "test_n": len(test_rows),
                    "train_end_ts": rows[train_idx[-1]]["ts"] if train_idx else None,
                    "test_start_ts": rows[test_idx[0]]["ts"], "test_end_ts": rows[test_idx[-1]]["ts"],
                    "hypotheses": scores})
    return {"status": "RESEARCH_ONLY", "label": label, "purge_bars": horizon,
            "embargo_bars": embargo, "costs_bps": dict(costs), "folds": out,
            "chronological": True, "auto_apply": False, "real_orders": False}


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists(): return []
    rows = []
    for line in path.read_text().splitlines():
        try: rows.append(json.loads(line))
        except json.JSONDecodeError: continue
    return rows


def main() -> None:
    candles = json.loads(CANDLES.read_text()) if CANDLES.exists() else []
    rows = build_rows(candles, load_jsonl(MICRO))
    outputs = {name: walk_forward(rows, name, min_train=120) for name in HORIZONS}
    labeled = {name: sum(name in r["labels"] for r in rows) for name in HORIZONS}
    result = {"version": "prediction_layer_v1", "status": "RESEARCH_ONLY",
              "source_candles": len(candles), "source_micro_rows": len(load_jsonl(MICRO)),
              "labeled_rows": labeled, "features": list(FEATURES),
              "costs_bps": dict(DEFAULT_COSTS), "walk_forward": outputs,
              "limitations": ["Microstructure features are omitted when stale or unavailable.",
                              "Walk-forward results are not decision-grade without adequate independent folds.",
                              "Candle timestamps are interpreted as bar-open timestamps; verify source convention."],
              "policy": {"leverage_changed": False, "risk_changed": False,
                         "execution_changed": False, "production_strategy_changed": False,
                         "order_placement": False}}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, allow_nan=False))
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__": main()
