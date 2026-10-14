"""Pre-registered directional filter screen for 300s cost-threshold labels.

Research-only. Uses no exchange API and cannot submit orders. Labels are mid-price
counterfactuals; outputs must not be interpreted as actual fill-based profitability.
"""
from __future__ import annotations
import json, math, statistics
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data/processed/cost_threshold_barrier_labels_v1.jsonl"
OUT = ROOT / "data/processed/cost_threshold_filter_screen_v1.json"
HORIZON = 300.0
COST_SCENARIOS_BPS = (11.8, 15.8)
RULES = ("delta30", "ret30", "imb10", "cvd", "confluence2of4",
         "confluence3of4", "pressure_cont", "absorption_rev")


def finite_num(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else 0.0
    except (TypeError, ValueError):
        return 0.0


def sign(value):
    return 1 if value > 0 else (-1 if value < 0 else 0)


def load_entries():
    pairs = {}
    with SRC.open(encoding="utf-8") as handle:
        for line in handle:
            try:
                item = json.loads(line)
                pairs.setdefault(float(item["ts"]), {})[item["side"]] = item
            except (ValueError, TypeError, KeyError):
                continue
    entries = []
    for ts, pair in sorted(pairs.items()):
        if "LONG" not in pair or "SHORT" not in pair:
            continue
        long_row = pair["LONG"]
        features = long_row.get("features") or {}
        entries.append({
            "ts": ts, "long": long_row, "short": pair["SHORT"],
            "imb10": finite_num(features.get("imb10")),
            "delta30": finite_num(features.get("delta30")),
            "ret30": finite_num(features.get("ret30")),
            "cvd": finite_num(features.get("cvd_slope30")),
            "regime": str(features.get("regime", "NEUTRAL")),
        })
    return entries


def direction(entry, rule):
    if rule == "delta30":
        return sign(entry["delta30"])
    if rule == "ret30":
        return sign(entry["ret30"])
    if rule == "imb10":
        return sign(entry["imb10"])
    if rule == "cvd":
        return sign(entry["cvd"])
    if rule in ("confluence2of4", "confluence3of4"):
        values = [sign(entry[key]) for key in ("delta30", "ret30", "imb10", "cvd")]
        score = sum(values)
        minimum = 2 if rule == "confluence2of4" else 3
        return sign(score) if abs(score) >= minimum else 0
    if rule == "pressure_cont":
        if entry["regime"] in ("BUY_PRESSURE", "BUYER_CONFIRMATION"):
            return 1
        if entry["regime"] in ("SELL_PRESSURE", "SELLER_CONFIRMATION"):
            return -1
        return 0
    if rule == "absorption_rev":
        if entry["regime"] == "BUYER_ABSORPTION":
            return 1
        if entry["regime"] == "SELLER_ABSORPTION":
            return -1
        return 0
    raise ValueError(f"unknown rule: {rule}")


def split_for(ts, q1, q2):
    if ts < q1 - HORIZON:
        return "train"
    if q1 + HORIZON < ts < q2 - HORIZON:
        return "validation"
    if ts > q2 + HORIZON:
        return "test"
    return None


def gross_outcome(row):
    # Barrier fills are fixed at the barrier, avoiding sampled-price overshoot.
    if row.get("class") == "TARGET_FIRST":
        return 20.0
    if row.get("class") == "STOP_FIRST":
        return -10.0
    return finite_num(row.get("terminal_move_bps"))


def summarize(trades, cost):
    net = [item["gross_bps"] - cost for item in trades]
    winners = [x for x in net if x > 0]
    losers = [x for x in net if x < 0]
    gross_profit = sum(winners)
    gross_loss = -sum(losers)
    equity = peak = max_drawdown = 0.0
    for value in net:
        equity += value
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
    classes = Counter(item["class"] for item in trades)
    return {
        "trades": len(net),
        "target_first": classes["TARGET_FIRST"],
        "stop_first": classes["STOP_FIRST"],
        "no_barrier_timeout": classes["ABSTAIN_NO_BARRIER"],
        "win_rate_pct": round(100 * len(winners) / len(net), 2) if net else None,
        "avg_net_bps": round(statistics.fmean(net), 3) if net else None,
        "median_net_bps": round(statistics.median(net), 3) if net else None,
        "profit_factor": round(gross_profit / gross_loss, 4) if gross_loss else (None if not gross_profit else "inf"),
        "total_net_bps": round(sum(net), 3),
        "max_drawdown_bps": round(max_drawdown, 3),
        "gross_avg_bps": round(statistics.fmean([item["gross_bps"] for item in trades]), 3) if trades else None,
    }


def screen(entries, rule, split, cost):
    # First signal wins; then skip 300 seconds so selected entries do not overlap.
    candidates = []
    for entry in entries:
        if split_for(entry["ts"], BOUNDARY_1, BOUNDARY_2) != split:
            continue
        side = direction(entry, rule)
        if side == 0:
            continue
        row = entry["long"] if side > 0 else entry["short"]
        candidates.append({
            "ts": entry["ts"], "class": row.get("class", "UNKNOWN"),
            "gross_bps": gross_outcome(row),
        })
    selected = []
    next_allowed = -math.inf
    for candidate in candidates:
        if candidate["ts"] >= next_allowed:
            selected.append(candidate)
            next_allowed = candidate["ts"] + HORIZON
    return summarize(selected, cost)


def main():
    global BOUNDARY_1, BOUNDARY_2
    entries = load_entries()
    if len(entries) < 100:
        raise SystemExit(f"Insufficient paired timestamps: {len(entries)}")
    timestamps = [item["ts"] for item in entries]
    BOUNDARY_1 = timestamps[int(0.60 * (len(timestamps) - 1))]
    BOUNDARY_2 = timestamps[int(0.80 * (len(timestamps) - 1))]
    results = []
    for rule in RULES:
        by_cost = {}
        for cost in COST_SCENARIOS_BPS:
            by_cost[str(cost)] = {
                split: screen(entries, rule, split, cost)
                for split in ("train", "validation", "test")
            }
        results.append({"rule": rule, "cost_scenarios_bps": by_cost})
    promoted = [
        result["rule"] for result in results
        if all(result["cost_scenarios_bps"][str(cost)][split]["trades"] >= 100
               and (result["cost_scenarios_bps"][str(cost)][split]["avg_net_bps"] or 0) > 0
               and isinstance(result["cost_scenarios_bps"][str(cost)][split]["profit_factor"], (int, float))
               and result["cost_scenarios_bps"][str(cost)][split]["profit_factor"] > 1.2
               for cost in COST_SCENARIOS_BPS for split in ("validation", "test"))
    ]
    report = {
        "schema": "cost_threshold_filter_screen_v1",
        "status": "NO_VALIDATED_EDGE" if not promoted else "CANDIDATES_REQUIRE_INDEPENDENT_REPLICATION",
        "research_only": True, "real_orders": False,
        "source": str(SRC.relative_to(ROOT)),
        "paired_entry_timestamps": len(entries),
        "chronological_boundaries_epoch": {"train_validation": BOUNDARY_1, "validation_test": BOUNDARY_2},
        "purge_seconds": HORIZON,
        "cost_scenarios_bps": list(COST_SCENARIOS_BPS),
        "rules": results,
        "promotion_candidates": promoted,
        "limitations": [
            "Single capture period; not independent multi-session replication.",
            "300-second labels overlap in the source; selected entries are spaced by 300 seconds but residual dependence remains.",
            "Targets/stops use fixed barrier outcomes; timeout exits use mid-price terminal return, not executable bid/ask.",
            "Cost scenarios are fixed assumptions; maker fill probability, queue priority, latency and fill-conditioned adverse selection are not observed.",
            "Threshold rules are a small pre-registered screen, not an exhaustive model search."
        ],
    }
    OUT.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(OUT.relative_to(ROOT)),
        "status": report["status"],
        "paired_entry_timestamps": len(entries),
        "promotion_candidates": promoted,
        "rule_count": len(results),
        "real_orders": False,
    }, indent=2))


if __name__ == "__main__":
    main()
