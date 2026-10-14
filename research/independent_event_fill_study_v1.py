"""Independent event/fill sensitivity study. Research only; no execution authority."""
from __future__ import annotations

import json
import math
import statistics
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from execution.fill_simulator import FillModel, simulate
from research.event_conditioned_edge_tournament_v1 import HORIZONS, event_flags, thresholds

LAB = ROOT / "data/processed/live_microstructure_labeled_v1.jsonl"
OUT = ROOT / "data/processed/independent_event_fill_study_v1.json"
MODEL = FillModel()
MIN_HOLDOUT_FILLS = 10
MIN_STABLE_N = 50
EVENT_TYPES = ("FLOW_PRICE_CONFIRM_LONG", "FLOW_PRICE_CONFIRM_SHORT", "ABSORPTION_LONG",
               "ABSORPTION_SHORT", "SWEEP_RECLAIM_LONG", "SWEEP_RECLAIM_SHORT",
               "DIVERGENCE_LONG", "DIVERGENCE_SHORT", "IMBALANCE_REVERSAL_LONG",
               "IMBALANCE_REVERSAL_SHORT")


def _num(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def load_rows(path: Path = LAB):
    rows = []
    if path.exists():
        for line in path.read_text().splitlines():
            try:
                row = json.loads(line)
                if isinstance(row, dict) and isinstance(row.get("labels"), dict):
                    rows.append(row)
            except (json.JSONDecodeError, TypeError):
                continue
    return sorted(rows, key=lambda row: _num(row.get("ts")) or 0.0)


def chronological_split(rows):
    cut = int(len(rows) * 0.60)
    train, holdout = rows[:cut], rows[cut:]
    return train, holdout, (_num(holdout[0].get("ts")) if holdout else None)


def purge_training_rows(train, holdout_start, horizon):
    """Remove outcomes crossing the holdout boundary; features remain training-only."""
    result = []
    for row in train:
        label = row.get("labels", {}).get(str(horizon), {})
        future_ts = _num(label.get("future_ts")) if isinstance(label, dict) else None
        if future_ts is not None and (holdout_start is None or future_ts <= holdout_start):
            result.append(row)
    return result


def select_non_overlapping(rows, event_name, horizon, fitted_thresholds, side):
    """Return eligible event observations and raw/nonoverlap/skip counts."""
    raw = []
    for row in rows:
        flags = event_flags(row, fitted_thresholds)
        if not flags.get(event_name, False):
            continue
        label = row.get("labels", {}).get(str(horizon), {})
        ts = _num(row.get("ts"))
        future_ts = _num(label.get("future_ts")) if isinstance(label, dict) else None
        move = _num(label.get("move_bps")) if isinstance(label, dict) else None
        if ts is not None and future_ts is not None and move is not None:
            raw.append((ts, future_ts, move * side, row))
    raw.sort(key=lambda item: item[0])
    selected, previous_future = [], -math.inf
    for observation in raw:
        if observation[0] >= previous_future:
            selected.append(observation)
            previous_future = observation[1]
    return selected, {"raw_event_count": len(raw), "non_overlapping_count": len(selected),
                      "skip_count": len(raw) - len(selected)}


def _stats(values):
    if not values:
        return None
    n = len(values)
    half = n // 2
    first = statistics.fmean(values[:half]) if half else None
    second = statistics.fmean(values[half:]) if n - half else None
    wins = sum(v > 0 for v in values)
    gains = sum(v for v in values if v > 0)
    losses = -sum(v for v in values if v < 0)
    mean = statistics.fmean(values)
    return {"sample_count": n, "net_mean_bps": mean,
            "win_rate": wins / n, "profit_factor": gains / losses if losses else None,
            "first_half_net_mean_bps": first, "second_half_net_mean_bps": second,
            "exploratory_stable_positive": bool(n >= MIN_STABLE_N and mean > 0 and first is not None
                                                 and second is not None and first > 0 and second > 0)}


def evaluate_route(observations, route, model=MODEL):
    # Midpoint grid is fixed, signal-order deterministic, and independent of global RNG.
    n = len(observations)
    rng_values = [((i + 0.5) / n) for i in range(n)] if n else []
    fills = []
    for i, (ts, future_ts, gross, row) in enumerate(observations):
        sim = simulate(gross, route, model=model, rng_value=rng_values[i] if route == "MAKER" else 0.0)
        if sim.filled:
            fills.append((ts, gross, sim.net_edge_bps, row))
    stats = _stats([item[2] for item in fills])
    gross_stats = statistics.fmean(item[1] for item in fills) if fills else None
    if stats:
        stats["gross_mean_bps"] = gross_stats
    result = {"route": route, "signal_count": n, "fill_count": len(fills),
              "fill_probability": len(fills) / n if n else None,
              "conditional_on_fill": stats}
    if route == "MAKER":
        p = model.maker_fill_probability
        result["expected_net_per_signal_bps"] = stats["net_mean_bps"] * p if stats else None
        result["fill_probability_configured"] = p
    else:
        result["expected_net_per_signal_bps"] = stats["net_mean_bps"] if stats else None
    # Diagnostic uses actual observed full spread (two half-spreads), fees only, no slippage.
    diagnostic = []
    for _, gross, _, row in fills:
        spread = _num(row.get("spread_bps"))
        if spread is not None:
            fee = 2 * (model.taker_fee_bps if route == "TAKER" else model.maker_fee_bps)
            diagnostic.append(gross - fee - spread)
    result["observed_spread_fee_only_diagnostic_mean_bps"] = statistics.fmean(diagnostic) if diagnostic else None
    result["observed_spread_fee_only_diagnostic_n"] = len(diagnostic)
    return result


def evaluate(rows):
    if len(rows) < 2:
        return {"schema": "independent_event_fill_study_v1", "error": "insufficient_rows", "rows_loaded": len(rows)}
    train, holdout, holdout_start = chronological_split(rows)
    fitted = thresholds(train)
    results, event_counts = [], []
    for horizon in HORIZONS:
        train_eligible = purge_training_rows(train, holdout_start, horizon)
        for event_name in EVENT_TYPES:
            side = 1 if event_name.endswith("LONG") else -1
            for split_name, split_rows in (("train", train_eligible), ("holdout", holdout)):
                obs, counts = select_non_overlapping(split_rows, event_name, horizon, fitted, side)
                event_counts.append({"split": split_name, "horizon_s": horizon,
                                     "event": event_name,
                                     "direction": "LONG" if side == 1 else "SHORT",
                                     **counts})
                for route in ("TAKER", "MAKER"):
                    routed = evaluate_route(obs, route)
                    if split_name == "holdout" and routed["fill_count"] < MIN_HOLDOUT_FILLS:
                        continue
                    results.append({"split": split_name, "horizon_s": horizon, "event": event_name,
                                    "direction": "LONG" if side == 1 else "SHORT",
                                    "non_overlap_counts": counts, **routed})
    bounds = lambda part: {"start_ts": _num(part[0].get("ts")) if part else None,
                           "end_ts": _num(part[-1].get("ts")) if part else None}
    return {"schema": "independent_event_fill_study_v1", "research_only": True,
            "real_orders": False, "rows_loaded": len(rows),
            "split": {"train_fraction": 0.60, "holdout_fraction": 0.40,
                      "train_rows": len(train), "holdout_rows": len(holdout),
                      "train_bounds": bounds(train), "holdout_bounds": bounds(holdout),
                      "holdout_start_ts": holdout_start,
                      "train_threshold_feature_rows": len(train),
                      "thresholds_fit_on_train_only": True,
                      "thresholds": fitted,
                      "purged_train_rows_by_horizon": {str(h): len(train) - len(purge_training_rows(train, holdout_start, h)) for h in HORIZONS}},
            "fill_model": {"maker_fee_bps": MODEL.maker_fee_bps, "taker_fee_bps": MODEL.taker_fee_bps,
                           "spread_bps": MODEL.spread_bps, "slippage_bps": MODEL.slippage_bps,
                           "adverse_selection_bps": MODEL.adverse_selection_bps,
                           "maker_fill_probability": MODEL.maker_fill_probability,
                           "maker_fill_sequence": "fixed sequential midpoint uniform grid; no global randomness",
                           "maker_caveat": "Does not model adverse selection conditional on fills or queue position accurately."},
            "holdout_minimum_fills": MIN_HOLDOUT_FILLS,
            "stability_rule": "positive only when net mean and both chronological half means > 0 and n >= 50; exploratory, not validated",
            "event_counts": event_counts, "results": results}


def main():
    result = evaluate(load_rows())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2))
    holdout = [r for r in result.get("results", []) if r["split"] == "holdout"]
    stable = [r for r in holdout if r.get("conditional_on_fill", {}).get("exploratory_stable_positive")]
    print(json.dumps({"rows_loaded": result.get("rows_loaded"), "reported_holdout_rows": len(holdout),
                      "exploratory_stable_candidates": len(stable),
                      "top_by_route": {route: [{"event": r["event"], "horizon_s": r["horizon_s"],
                         "n": r["fill_count"], "net_mean_bps": r["conditional_on_fill"]["net_mean_bps"],
                         "first_half_net_mean_bps": r["conditional_on_fill"]["first_half_net_mean_bps"],
                         "second_half_net_mean_bps": r["conditional_on_fill"]["second_half_net_mean_bps"]}
                         for r in sorted((x for x in holdout if x["route"] == route),
                                         key=lambda x: x["conditional_on_fill"]["net_mean_bps"], reverse=True)[:5]]
                         for route in ("TAKER", "MAKER")}}, indent=2))


if __name__ == "__main__":
    main()
