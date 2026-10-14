"""Exploratory, purged train/holdout sensitivity study for regime thresholds.

Reads only the historical labeled microstructure rows. This is a diagnostic
multiple-comparisons exercise and makes no validated edge or strategy claim.
"""
from __future__ import annotations

import itertools
import json
import math
from pathlib import Path
from typing import Any

from opportunity_regime_discovery_v1 import HORIZONS, ROUND_TRIP_FEE_BPS, _num, load_jsonl

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data/processed/live_microstructure_labeled_v1.jsonl"
DEFAULT_OUTPUT = ROOT / "data/processed/opportunity_regime_sensitivity_v1.json"
GRID = {
    "volatility_bps": (1, 3, 5, 10),
    "divergence_bps": (0.5, 1, 2),
    "toxicity_bps": (0.5, 1, 2),
    "trend_bps": (1, 2, 3),
}
MIN_TRAIN = 20
MIN_HOLDOUT = 10
DIMENSIONS = ("volatility", "divergence", "toxicity", "trend")


def settings() -> list[dict[str, float]]:
    return [dict(zip(GRID, vals)) for vals in itertools.product(*GRID.values())]


def threshold_state(row: dict[str, Any], setting: dict[str, float]) -> tuple[str, ...]:
    # Source ret fields are percentage points; convert once to decimal, then to bps.
    r5, r30, r60 = (_num(row, key) / 100.0 for key in ("ret5", "ret30", "ret60"))
    r5_bps, r30_bps, r60_bps = (abs(x) * 10_000 for x in (r5, r30, r60))
    d5, d30 = _num(row, "delta5"), _num(row, "delta30")
    volatility = "high_vol" if r60_bps >= setting["volatility_bps"] else "low_vol"
    divergence = "divergent" if d30 * r30 < 0 and r30_bps >= setting["divergence_bps"] else "aligned"
    toxicity = "toxic" if d5 * r5 < 0 and r5_bps >= setting["toxicity_bps"] else "non_toxic"
    trend = "trend" if r5 * r30 > 0 and r30_bps >= setting["trend_bps"] else "mean_reversion" if r5 * r30 < 0 else "flat"
    return volatility, divergence, toxicity, trend


def metrics(values: list[float]) -> dict[str, Any]:
    wins = sum(x for x in values if x > 0)
    loss = -sum(x for x in values if x <= 0)
    return {"n": len(values), "mean_net_bps": sum(values) / len(values) if values else None,
            "profit_factor": wins / loss if loss else ("inf" if wins else None)}


def _valid(row: dict[str, Any], horizon: str) -> bool:
    lab = row.get("labels", {}).get(horizon)
    return isinstance(lab, dict) and "move_bps" in lab and math.isfinite(_num(lab, "move_bps", math.nan))


def _net(row: dict[str, Any], horizon: str, side: int, fee: float) -> float:
    return side * _num(row["labels"][horizon], "move_bps") - fee - 2 * _num(row, "spread_bps")


def analyze(rows: list[dict[str, Any]], fee_bps_roundtrip: float = ROUND_TRIP_FEE_BPS) -> dict[str, Any]:
    ordered = sorted((r for r in rows if isinstance(r.get("labels"), dict) and _num(r, "ts", math.nan) == _num(r, "ts", math.nan)), key=lambda r: _num(r, "ts"))
    split = int(len(ordered) * 0.6)
    train_base, holdout = ordered[:split], ordered[split:]
    grid = settings()
    # Keep only one setting's classifications in memory at a time. The labeled
    # tape can be large on constrained research machines.
    holdout_start = _num(holdout[0], "ts", math.nan) if holdout else None
    candidates, baselines = [], []
    for horizon in HORIZONS:
        for side, direction in ((1, "long"), (-1, "short")):
            test = [r for r in holdout if _valid(r, horizon)]
            baselines.append({"horizon_seconds": int(horizon), "direction": direction, **metrics([_net(r, horizon, side, fee_bps_roundtrip) for r in test])})
    for setting in grid:
        states = [threshold_state(row, setting) for row in ordered]
        for horizon in HORIZONS:
            for side, direction in ((1, "long"), (-1, "short")):
                train_indices = [i for i, r in enumerate(train_base) if _valid(r, horizon) and _num(r["labels"][horizon], "future_ts", math.inf) <= (holdout_start if holdout_start is not None else -math.inf)]
                hold_indices = [i for i in range(split, len(ordered)) if _valid(ordered[i], horizon)]
                buckets: dict[tuple[str, ...], list[dict[str, Any]]] = {}
                for i in train_indices:
                    buckets.setdefault(states[i], []).append(train_base[i])
                eligible = [(key, members) for key, members in buckets.items() if len(members) >= MIN_TRAIN]
                if not eligible:
                    continue
                # Fixed training-only criterion: highest training mean net return; deterministic tie break.
                key, members = max(eligible, key=lambda item: (sum(_net(r, horizon, side, fee_bps_roundtrip) for r in item[1]) / len(item[1]), item[0]))
                train_stats = metrics([_net(r, horizon, side, fee_bps_roundtrip) for r in members])
                held = [ordered[i] for i in hold_indices if states[i] == key]
                entry = {"setting": setting, "state": dict(zip(DIMENSIONS, key)), "horizon_seconds": int(horizon), "direction": direction,
                         "train": train_stats, "holdout": metrics([_net(r, horizon, side, fee_bps_roundtrip) for r in held]) if len(held) >= MIN_HOLDOUT else None}
                candidates.append(entry)
    evaluated = [c for c in candidates if c["holdout"] is not None]
    ranked = sorted(evaluated, key=lambda c: (c["holdout"]["mean_net_bps"], c["holdout"]["n"]), reverse=True)
    positive = [c for c in evaluated if c["holdout"]["mean_net_bps"] > 0 and c["holdout"]["profit_factor"] not in (None,) and (c["holdout"]["profit_factor"] == "inf" or c["holdout"]["profit_factor"] > 0)]
    def bounds(part):
        return {"rows": len(part), "start_ts": _num(part[0], "ts") if part else None, "end_ts": _num(part[-1], "ts") if part else None}
    return {"status": "exploratory_research_only", "input_rows": len(rows), "chronological_rows": len(ordered),
            "settings_count": len(grid), "grid": {k: list(v) for k, v in GRID.items()},
            "minimums": {"training": MIN_TRAIN, "holdout": MIN_HOLDOUT},
            "split": {"rule": "first 60% train, final 40% strict holdout", "train": bounds(train_base), "holdout": bounds(holdout), "holdout_start_ts": holdout_start,
                      "purge": "for each horizon, exclude training labels with future_ts after holdout start; equality is retained"},
            "cost_model": {"round_trip_fee_bps": fee_bps_roundtrip, "observed_spreads": 2},
            "selection": "For each setting/horizon/direction, select the eligible state with highest training mean net return only; ties use lexical state order.",
            "selected_candidates_training_only": len(candidates), "holdout_evaluable_candidates": len(evaluated),
            "any_positive_mean_and_positive_pf_on_holdout": bool(positive), "positive_holdout_candidates": len(positive),
            "candidates_selected_using_training_only": candidates,
            "baseline_holdout": baselines,
            "best_holdout_candidates_diagnostic_only_multiple_comparisons": ranked[:20],
            "caveat": "Holdout rankings are diagnostic only and exposed to multiple comparisons across 108 settings; this exploratory study does not validate an edge or select a deployable threshold."}


def run(input_path: Path = DEFAULT_INPUT, output_path: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    report = analyze(load_jsonl(input_path))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
