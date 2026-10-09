"""Research-only discovery of microstructure state cohorts.

Inputs are contemporaneous feature rows and precomputed forward labels. Feature
thresholds are fixed a priori; no label-derived fitting or execution hooks exist.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data/processed/live_microstructure_labeled_v1.jsonl"
DEFAULT_OUTPUT = ROOT / "data/processed/opportunity_regime_discovery_v1.json"
HORIZONS = ("60", "120", "180", "300")
ROUND_TRIP_FEE_BPS = 11.8
MIN_COHORT = 12


def _num(row: dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        value = float(row.get(key, default))
        return value if math.isfinite(value) else default
    except (TypeError, ValueError):
        return default


def state(row: dict[str, Any]) -> tuple[str, ...]:
    """Map only present-time fields to a fixed, interpretable regime."""
    # Labeled source rows store returns as percent points; thresholds below
    # use decimal returns, so convert only in this discovery consumer.
    r5, r30, r60 = (_num(row, k) / 100.0 for k in ("ret5", "ret30", "ret60"))
    d5, d30 = (_num(row, k) for k in ("delta5", "delta30"))
    imb = _num(row, "imb5")
    spread = _num(row, "spread_bps")
    # Scale decimal returns to bps for volatility.
    volatility = "high_vol" if abs(r60) * 10000 >= 3 else "low_vol"
    spr = "wide_spread" if spread >= 1.0 else "tight_spread"
    liquidity = "bid_heavy" if imb >= .2 else "ask_heavy" if imb <= -.2 else "balanced_liquidity"
    accel = d5 - d30
    flow = "buy_accel" if accel >= .25 else "sell_accel" if accel <= -.25 else "stable_flow"
    divergence = d30 * r30 < 0 and abs(d30) >= .2 and abs(r30) >= .0001
    div = "flow_price_divergence" if divergence else "flow_price_aligned"
    # Toxicity proxy: strong near-term flow opposed by recent price action.
    toxicity = "toxic_flow" if d5 * r5 < 0 and abs(d5) >= .5 and abs(r5) >= .0001 else "non_toxic_flow"
    trend = "trend" if r5 * r30 > 0 and abs(r30) >= .0002 else "mean_reversion" if r5 * r30 < 0 else "flat"
    return volatility, spr, liquidity, flow, div, toxicity, trend


def _metrics(values: list[float]) -> dict[str, Any]:
    wins = [x for x in values if x > 0]
    losses = [x for x in values if x <= 0]
    gross_loss = -sum(losses)
    return {"n": len(values), "net_bps": round(sum(values), 4),
            "avg_net_bps": round(sum(values) / len(values), 4) if values else None,
            "profit_factor": round(sum(wins) / gross_loss, 4) if gross_loss else (None if not wins else "inf"),
            "win_rate": round(len(wins) / len(values), 4) if values else None}


def _purged_folds(rows: list[dict[str, Any]], horizon: str, side: int, cost: float) -> list[dict[str, Any]]:
    """Chronological 4-fold validation; purge each validation horizon from train boundary."""
    out = []
    n = len(rows)
    for fold in range(4):
        lo, hi = fold * n // 4, (fold + 1) * n // 4
        chunk = rows[lo:hi]
        # A forward label may overlap the next horizon seconds. Drop boundary rows
        # from the validation block, a conservative purge using timestamp metadata.
        if hi < n and chunk:
            boundary = _num(rows[hi], "ts")
            chunk = [r for r in chunk if float(r.get("labels", {}).get(horizon, {}).get("future_ts", _num(r, "ts"))) <= boundary]
        vals = [side * _num(r["labels"][horizon], "move_bps") - cost for r in chunk if horizon in r.get("labels", {})]
        out.append({"fold": fold + 1, "n": len(vals), **_metrics(vals)})
    return out


def discover(rows: list[dict[str, Any]], fee_bps_roundtrip: float = ROUND_TRIP_FEE_BPS) -> dict[str, Any]:
    costs = {}
    # Cross the spread on entry and exit: two spreads plus round-trip fees.
    cohorts: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for row in rows:
        if not isinstance(row.get("labels"), dict):
            continue
        cohorts.setdefault(state(row), []).append(row)
    results = []
    for key, members in cohorts.items():
        members.sort(key=lambda r: _num(r, "ts"))
        mid = len(members) // 2
        for horizon in HORIZONS:
            valid = [r for r in members if horizon in r["labels"] and "move_bps" in r["labels"][horizon]]
            if not valid:
                continue
            for side, name in ((1, "long"), (-1, "short")):
                net = [side * _num(r["labels"][horizon], "move_bps") - fee_bps_roundtrip - 2 * _num(r, "spread_bps") for r in valid]
                if len(net) < MIN_COHORT:
                    continue
                half_a, half_b = net[:mid], net[mid:]
                results.append({"state": dict(zip(("volatility", "spread", "liquidity", "flow", "divergence", "toxicity", "trend"), key)),
                    "horizon_seconds": int(horizon), "direction": name, "cost_model": "round_trip_fee_plus_two_spreads",
                    "cost_bps": round(fee_bps_roundtrip + 2 * sum(_num(r, "spread_bps") for r in valid) / len(valid), 4),
                    **_metrics(net), "half_split": {"first": _metrics(half_a), "second": _metrics(half_b),
                    "stable_positive": bool(half_a and half_b and sum(half_a) > 0 and sum(half_b) > 0)},
                    "purged_chronological_folds": _purged_folds(valid, horizon, side,
                       fee_bps_roundtrip + 2 * sum(_num(r, "spread_bps") for r in valid) / len(valid))})
    results.sort(key=lambda x: (x["avg_net_bps"] if x["avg_net_bps"] is not None else -math.inf), reverse=True)
    return {"status": "research_only", "input_rows": len(rows), "labeled_rows": sum(bool(r.get("labels")) for r in rows),
            "cost_assumptions": {"round_trip_fee_bps": fee_bps_roundtrip, "spread_crossings": 2},
            "state_dimensions": ["volatility", "spread", "liquidity_imbalance", "flow_acceleration", "flow_divergence", "toxicity_proxy", "trend_mean_reversion"],
            "minimum_cohort_samples": MIN_COHORT, "cohorts_evaluated": len(results), "results": results}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open() as stream:
        for line in stream:
            try:
                obj = json.loads(line)
                if isinstance(obj, dict): rows.append(obj)
            except json.JSONDecodeError:
                continue
    return rows


def run(input_path: Path = DEFAULT_INPUT, output_path: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    report = discover(load_jsonl(input_path))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
