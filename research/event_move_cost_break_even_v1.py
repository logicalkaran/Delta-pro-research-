"""Auditable, research-only analysis of event moves versus execution costs."""
from __future__ import annotations

import json
import math
import statistics
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from execution.fill_simulator import FillModel, simulate

LAB = ROOT / "data/processed/live_microstructure_labeled_v1.jsonl"
OUT = ROOT / "data/processed/event_move_cost_break_even_v1.json"
HORIZONS = (60, 120, 180, 300)
MIN_SAMPLE = 30
EVENT_TYPES = (
    "FLOW_PRICE_CONFIRM_LONG", "FLOW_PRICE_CONFIRM_SHORT", "ABSORPTION_LONG",
    "ABSORPTION_SHORT", "SWEEP_RECLAIM_LONG", "SWEEP_RECLAIM_SHORT",
    "DIVERGENCE_LONG", "DIVERGENCE_SHORT", "IMBALANCE_REVERSAL_LONG",
    "IMBALANCE_REVERSAL_SHORT",
)
MODEL = FillModel()


def num(value):
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
    return sorted(rows, key=lambda row: num(row.get("ts")) or 0.0)


def chronological_split(rows):
    cut = int(len(rows) * 0.60)
    train, holdout = rows[:cut], rows[cut:]
    return train, holdout, num(holdout[0].get("ts")) if holdout else None


def purge_training_rows(train, holdout_start, horizon):
    kept = []
    for row in train:
        label = row.get("labels", {}).get(str(horizon), {})
        end = num(label.get("future_ts")) if isinstance(label, dict) else None
        if end is not None and (holdout_start is None or end <= holdout_start):
            kept.append(row)
    return kept


def thresholds(train):
    def quantile(key, p):
        values = sorted(v for v in (num(r.get(key)) for r in train) if v is not None)
        if len(values) < 20:
            return 0.0
        return values[(len(values) - 1) * p // 100] if (len(values) - 1) * p % 100 == 0 else _interp(values, (len(values) - 1) * p / 100)
    out = {"imb_hi": quantile("imb5", 75), "imb_lo": quantile("imb5", 25),
           "d30_hi": quantile("delta30", 75), "d30_lo": quantile("delta30", 25),
           "d5_hi": quantile("delta5", 75), "d5_lo": quantile("delta5", 25),
           "ret30_hi": quantile("ret30", 75), "ret30_lo": quantile("ret30", 25),
           "ret5_hi": quantile("ret5", 75), "ret5_lo": quantile("ret5", 25)}
    out["ret30_abs"] = max(abs(out["ret30_hi"]), abs(out["ret30_lo"])) * 0.35
    return out


def _interp(values, index):
    lo = int(index)
    return values[lo] + (values[lo + 1] - values[lo]) * (index - lo)


def event_flags(row, q):
    imb, d5, d30 = (num(row.get(k)) for k in ("imb5", "delta5", "delta30"))
    r5, r30 = (num(row.get(k)) for k in ("ret5", "ret30"))
    if None in (imb, d5, d30, r5, r30):
        return {}
    return {
        "FLOW_PRICE_CONFIRM_LONG": d30 >= q["d30_hi"] and r30 >= q["ret30_hi"] and imb >= q["imb_hi"],
        "FLOW_PRICE_CONFIRM_SHORT": d30 <= q["d30_lo"] and r30 <= q["ret30_lo"] and imb <= q["imb_lo"],
        "ABSORPTION_LONG": d30 >= q["d30_hi"] and abs(r30) <= q["ret30_abs"],
        "ABSORPTION_SHORT": d30 <= q["d30_lo"] and abs(r30) <= q["ret30_abs"],
        "SWEEP_RECLAIM_LONG": r5 <= q["ret5_lo"] and r30 >= 0 and imb >= q["imb_hi"],
        "SWEEP_RECLAIM_SHORT": r5 >= q["ret5_hi"] and r30 <= 0 and imb <= q["imb_lo"],
        "DIVERGENCE_LONG": d30 >= q["d30_hi"] and r30 <= q["ret30_lo"],
        "DIVERGENCE_SHORT": d30 <= q["d30_lo"] and r30 >= q["ret30_hi"],
        "IMBALANCE_REVERSAL_LONG": imb >= q["imb_hi"] and d5 >= q["d5_hi"] and r5 >= 0,
        "IMBALANCE_REVERSAL_SHORT": imb <= q["imb_lo"] and d5 <= q["d5_lo"] and r5 <= 0,
    }


def select_non_overlapping(rows, event, horizon, fitted, side):
    candidates = []
    for row in rows:
        if not event_flags(row, fitted).get(event, False):
            continue
        label = row.get("labels", {}).get(str(horizon), {})
        ts, future, move = num(row.get("ts")), num(label.get("future_ts")), num(label.get("move_bps"))
        if None not in (ts, future, move) and future >= ts:
            candidates.append((ts, future, move * side, row))
    candidates.sort(key=lambda x: x[0])
    selected, end = [], -math.inf
    for candidate in candidates:
        if candidate[0] >= end:
            selected.append(candidate)
            end = candidate[1]
    return selected, {"raw_event_count": len(candidates), "non_overlapping_count": len(selected),
                      "skip_count": len(candidates) - len(selected)}


def _mean(values):
    return statistics.fmean(values) if values else None


def _median(values):
    return statistics.median(values) if values else None


def _summary(obs, cost, route, stability_cut):
    gross = [x[2] for x in obs]
    spread = [num(x[3].get("spread_bps")) for x in obs]
    fee_total = (2 * MODEL.taker_fee_bps if route == "TAKER" else
                 MODEL.maker_fee_bps + MODEL.taker_fee_bps)
    diagnostic = [g - fee_total - s for g, s in zip(gross, spread) if s is not None]
    required_diagnostic = [fee_total + s for s in spread if s is not None]
    fill_probability = 1.0 if route == "TAKER" else MODEL.maker_fill_probability
    conditional_net_mean = _mean([x - cost for x in gross])
    first, second = [], []
    for item in obs:
        (first if item[0] < stability_cut else second).append(item[2])
    return {
        "sample_count": len(gross), "gross_mean_conditional_on_fill_bps": _mean(gross),
        "gross_median_conditional_on_fill_bps": _median(gross),
        "directional_hit_rate": sum(x > 0 for x in gross) / len(gross) if gross else None,
        "mfe_bps": None, "mae_bps": None,
        "mfe_mae_availability": "unavailable: labels contain endpoint move/future timestamp only; no path extrema",
        "full_cost": {"assumed_round_trip_cost_bps": cost,
                      "conditional_net_mean_bps": conditional_net_mean,
                      "expected_net_per_signal_bps": fill_probability * conditional_net_mean,
                      "maker_fill_probability": fill_probability if route == "MAKER" else None,
                      "required_gross_move_bps_to_break_even": cost},
        "observed_spread_fees_only": {"sample_count": len(diagnostic), "conditional_net_mean_bps": _mean(diagnostic),
                                       "required_gross_move_mean_bps": _mean(required_diagnostic),
                                       "assumption": ("two taker fees plus observed spread_bps once" if route == "TAKER" else
                                                      "maker entry fee plus taker exit fee and observed spread_bps once") + "; no slippage/adverse selection"},
        "chronological_holdout_halves": {"cut_ts": stability_cut,
                "first_half_n": len(first), "first_half_gross_mean_conditional_on_fill_bps": _mean(first),
            "first_half_full_cost_net_mean_conditional_on_fill_bps": _mean([x - cost for x in first]),
            "second_half_n": len(second), "second_half_gross_mean_conditional_on_fill_bps": _mean(second),
            "second_half_full_cost_net_mean_conditional_on_fill_bps": _mean([x - cost for x in second])},
    }


def _timestamp_audit(rows):
    ts = [num(r.get("ts")) for r in rows]
    valid = sorted(x for x in ts if x is not None)
    gaps = [b - a for a, b in zip(valid, valid[1:])]
    regime = Counter(str(r.get("regime")) for r in rows if r.get("regime") is not None)
    return {"row_count": len(rows), "valid_timestamp_count": len(valid),
            "missing_or_invalid_timestamp_count": len(rows) - len(valid),
            "start_ts": valid[0] if valid else None, "end_ts": valid[-1] if valid else None,
            "duration_seconds": valid[-1] - valid[0] if valid else None,
            "duration_hours": (valid[-1] - valid[0]) / 3600 if valid else None,
            "duplicated_timestamp_rows": len(valid) - len(set(valid)),
            "out_of_order_adjacent_pairs_in_source": sum(a is not None and b is not None and a > b for a, b in zip(ts, ts[1:])),
            "gap_seconds": {"count": len(gaps), "min": min(gaps) if gaps else None,
                            "median": _median(gaps), "p95": _interp(sorted(gaps), .95 * (len(gaps) - 1)) if gaps else None,
                            "max": max(gaps) if gaps else None, "over_2_seconds": sum(g > 2 for g in gaps),
                            "over_5_seconds": sum(g > 5 for g in gaps)},
            "explicit_session_field": False, "session_coverage": "unavailable: no session field",
            "regime_counts": dict(sorted(regime.items())),
            "regime_field_coverage": sum(r.get("regime") is not None for r in rows),
            "session_interpretation": "Single capture of the duration above; UTC clock coverage is not evidence of multiple sessions."}


def _missingness(rows):
    fields = ("ts", "mid", "spread_bps", "imb5", "delta5", "delta30", "ret5", "ret30", "regime", "labels")
    out = {key: {"missing_or_null": sum(r.get(key) is None for r in rows), "coverage": sum(r.get(key) is not None for r in rows)} for key in fields}
    for h in HORIZONS:
        out[f"label_{h}s"] = {"missing_or_null": sum(not isinstance(r.get("labels", {}).get(str(h)), dict) for r in rows),
                              "coverage": sum(isinstance(r.get("labels", {}).get(str(h)), dict) for r in rows)}
    return out


def evaluate(rows):
    train, holdout, holdout_start = chronological_split(rows)
    fitted = thresholds(train)
    cut = holdout[0]["ts"] + (holdout[-1]["ts"] - holdout[0]["ts"]) / 2 if holdout else None
    results, counts = [], []
    tested = 0
    for horizon in HORIZONS:
        purified = purge_training_rows(train, holdout_start, horizon)
        for event in EVENT_TYPES:
            side = 1 if event.endswith("LONG") else -1
            for split_name, subset in (("train_purged", purified), ("holdout", holdout)):
                obs, count = select_non_overlapping(subset, event, horizon, fitted, side)
                counts.append({"split": split_name, "horizon_s": horizon, "event": event, **count})
                if split_name != "holdout":
                    continue
                tested += 1
                if len(obs) < MIN_SAMPLE:
                    continue
                for route in ("TAKER", "MAKER"):
                    sim = simulate(0, route, MODEL)
                    results.append({"split": "holdout", "horizon_s": horizon, "event": event,
                                    "direction": "LONG" if side == 1 else "SHORT",
                                    "non_overlap_counts": count,
                                    "metrics": _summary(obs, sim.total_cost_bps,
                                                        route, cut), "route": route})
    duration = _timestamp_audit(rows)
    label_keys = sorted({key for r in rows for key in (r.get("labels") or {})})
    return {"schema": "event_move_cost_break_even_v1", "research_only": True, "real_orders": False,
            "rows_loaded": len(rows), "data_audit": duration, "missingness": _missingness(rows),
            "label_definition": {"source": "research/live_microstructure_labeler_v1.py",
                "available_horizons_s": label_keys,
                "move_bps": "(future_mid / current_mid - 1) * 10000; nearest observed mid at or after ts+horizon",
                "forward_label_fields": sorted({k for r in rows for lab in (r.get("labels") or {}).values() if isinstance(lab, dict) for k in lab}),
                "path_mfe_mae": "unavailable from saved labels; no intrahorizon price path retained"},
            "split": {"train_fraction": .60, "holdout_fraction": .40, "train_rows": len(train),
                "holdout_rows": len(holdout), "holdout_start_ts": holdout_start,
                "thresholds_fit_on_train_only": True, "thresholds": fitted,
                "purge_rule": "training label future_ts <= first holdout timestamp",
                "purged_train_rows_by_horizon": {str(h): len(train) - len(purge_training_rows(train, holdout_start, h)) for h in HORIZONS}},
            "cost_assumptions": {"source": "execution/fill_simulator.py FillModel",
                "taker": {"fee_bps_per_side": MODEL.taker_fee_bps, "spread_bps_per_side": MODEL.spread_bps / 2,
                          "slippage_bps_per_side": MODEL.slippage_bps,
                          "adverse_selection_bps": 0, "round_trip_total_bps": simulate(0, "TAKER", MODEL).total_cost_bps},
                "maker_entry_fee_bps": MODEL.maker_fee_bps, "maker_entry_spread_bps": MODEL.spread_bps * .25,
                "maker_entry_adverse_selection_bps": MODEL.adverse_selection_bps,
                "maker_exit_assumes_taker_fee_and_half_spread": True,
                "maker_round_trip_total_bps": simulate(0, "MAKER", MODEL).total_cost_bps,
                "maker_fill_probability": MODEL.maker_fill_probability,
                "maker_costs_conditional_on_fill; no queue/conditional adverse selection modeled": True},
            "minimum_sample_rule": {"holdout_non_overlapping_entries": MIN_SAMPLE,
                "reported_combinations": "all event/horizon/route combinations meeting the rule",
                "tested_event_horizon_combinations": tested,
                "eligible_event_horizon_combinations": sum(1 for x in results if x["route"] == "TAKER"),
                "multiple_comparisons_caveat": "Exploratory screen across 40 event/horizon combinations and two routes; no correction or independent replication."},
            "diagnostic_limits": {"direction_vs_size": "hit rate and gross magnitude are reported; endpoint labels do not reveal path ordering",
                "adverse_excursion": "unavailable without intrahorizon path data",
                "latency": "unavailable: no signal-to-order/arrival latency observations",
                "holding_horizon": "endpoint outcomes available at 60/120/180/300 seconds only",
                "cost_burden": "compare gross endpoint return with explicit model costs and observed spread/fees-only diagnostic"},
            "event_counts_all_combinations": counts, "results": results,
            "conclusion": "No edge claim. This short single-capture study is descriptive; MFE/MAE, latency attribution, session generalization, and independent replication are unavailable."}


def main():
    OUT.write_text(json.dumps(evaluate(load_rows()), indent=2) + "\n")


if __name__ == "__main__":
    main()
