"""Offline event study for cross-venue sweep labels; research-only, no execution."""
from __future__ import annotations
import argparse
import json
import math
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIR = ROOT / "data/raw/cross_venue_aligned"
HORIZONS = (5, 15, 30)


def read_jsonl(path):
    rows = []
    if not path or not Path(path).exists():
        return rows
    with Path(path).open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return rows


def pct(values, p):
    if not values:
        return None
    a = sorted(values)
    pos = (len(a) - 1) * p / 100
    lo = int(pos); hi = min(lo + 1, len(a) - 1)
    return a[lo] + (a[hi] - a[lo]) * (pos - lo)


def summarize(values):
    if not values:
        return {"n": 0, "mean_bps": None, "median_bps": None,
                "positive_pct": None, "p10_bps": None, "p90_bps": None}
    return {
        "n": len(values),
        "mean_bps": statistics.fmean(values),
        "median_bps": statistics.median(values),
        "positive_pct": 100 * sum(v > 0 for v in values) / len(values),
        "p10_bps": pct(values, 10),
        "p90_bps": pct(values, 90),
    }


def valid_quote(row):
    return (row.get("venue") in ("binance", "delta")
            and row.get("receive_mono_s") is not None
            and isinstance(row.get("mid"), (int, float))
            and row["mid"] > 0
            and row.get("kind") in ("depthUpdate", "ob_l1"))


def make_timeline(raw):
    rows = sorted((r for r in raw if valid_quote(r)),
                  key=lambda r: r["receive_mono_s"])
    by_venue = {"binance": [], "delta": []}
    for r in rows:
        by_venue[r["venue"]].append(r)
    return by_venue


def latest_at(rows, target, max_age=1.0):
    chosen = None
    for r in rows:
        if r["receive_mono_s"] > target:
            break
        chosen = r
    if chosen is None or target - chosen["receive_mono_s"] > max_age:
        return None
    return chosen


def future_at(rows, target, max_age=1.0):
    for r in rows:
        if r["receive_mono_s"] >= target:
            if r["receive_mono_s"] - target <= max_age:
                return r
            return None
    return None


def return_bps(a, b):
    if not a or not b or a["mid"] <= 0 or b["mid"] <= 0:
        return None
    return 10000 * math.log(b["mid"] / a["mid"])


def matched_baseline(by_venue):
    """Non-overlapping 30s anchors, with a 1s buffer and strict quote freshness."""
    b, d = by_venue["binance"], by_venue["delta"]
    if not b or not d:
        return {h: [] for h in HORIZONS}
    start = max(b[0]["receive_mono_s"], d[0]["receive_mono_s"])
    end = min(b[-1]["receive_mono_s"], d[-1]["receive_mono_s"])
    samples = {h: [] for h in HORIZONS}
    anchor = start
    while anchor + 1 + 30 <= end:
        base_t = anchor + 1.0
        base = {v: future_at(by_venue[v], base_t) for v in ("binance", "delta")}
        if all(base.values()):
            for h in HORIZONS:
                target_t = base_t + h
                target = {v: future_at(by_venue[v], target_t) for v in ("binance", "delta")}
                if all(target.values()):
                    samples[h].append({
                        "binance_bps": return_bps(base["binance"], target["binance"]),
                        "delta_bps": return_bps(base["delta"], target["delta"]),
                    })
        anchor += 30.0
    return samples


def timestamp_diagnostics(raw):
    samples = {"binance": [], "delta": []}
    for row in raw:
        venue = row.get("venue")
        recv = row.get("receive_epoch_s")
        if venue == "binance":
            engine = row.get("engine_transaction_ts_s") or row.get("engine_event_ts_s")
        elif venue == "delta":
            engine = row.get("engine_ts_s") or row.get("engine_trade_ts_s") or row.get("feed_ts_s")
        else:
            continue
        if isinstance(recv, (int, float)) and isinstance(engine, (int, float)):
            samples[venue].append((recv - engine) * 1000)
    result = {}
    for venue, values in samples.items():
        ordered = sorted(values)
        result[venue] = {
            "n": len(values),
            "receive_minus_engine_ms_median": statistics.median(values) if values else None,
            "p10_ms": pct(values, 10),
            "p90_ms": pct(values, 90),
            "negative_samples": sum(x < 0 for x in values),
            "interpretation": "local wall-clock offset + timestamp semantics + delivery delay; NOT one-way network latency",
        }
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", required=True, help="UTC session stamp, e.g. 20261009T173031Z")
    ap.add_argument("--data-dir", default=str(DEFAULT_DIR))
    ap.add_argument("--output", default=None)
    args = ap.parse_args()
    base = Path(args.data_dir)
    raw_path = base / f"cross_venue_ticks_{args.session}.jsonl"
    sweep_path = base / f"cross_venue_sweeps_{args.session}.jsonl"
    labels_path = base / f"cross_venue_labels_{args.session}.jsonl"
    raw = read_jsonl(raw_path)
    sweeps = read_jsonl(sweep_path)
    labels = read_jsonl(labels_path)
    by_venue = make_timeline(raw)
    baseline = matched_baseline(by_venue)
    report = {
        "schema": "cross_venue_event_study_v1",
        "session": args.session,
        "mode": "OFFLINE_RESEARCH_ONLY",
        "inputs": {"raw_rows": len(raw), "sweep_candidates": len(sweeps),
                   "label_rows": len(labels),
                   "binance_quote_rows": len(by_venue["binance"]),
                   "delta_quote_rows": len(by_venue["delta"])},
        "timestamp_diagnostics": timestamp_diagnostics(raw),
        "event_outcomes": {},
        "matched_non_event_baseline": {},
        "interpretation": [
            "Directional follow-through is gross mid-price movement, not executable PnL.",
            "The non-event baseline uses non-overlapping 30s anchors, a 1s buffer, and quotes no more than 1s stale.",
            "Sample counts are likely too small for inference; this report does not establish predictive edge.",
            "No fees, queue position, fill probability, contract multiplier, or funding are assumed."
        ],
        "production_changes": False,
        "real_orders": False,
    }
    for h in HORIZONS:
        key = f"{h}s"
        event_delta = []
        event_binance = []
        event_diff = []
        for row in labels:
            outcome = row.get("outcomes", {}).get(key, {})
            if row.get("status") != "OK":
                continue
            direction = row.get("direction")
            dv = outcome.get("delta_log_return_bps")
            bv = outcome.get("binance_log_return_bps")
            diff = outcome.get("return_differential_binance_minus_delta_bps")
            if isinstance(dv, (int, float)) and isinstance(direction, (int, float)):
                event_delta.append(direction * dv)
            if isinstance(bv, (int, float)) and isinstance(direction, (int, float)):
                event_binance.append(direction * bv)
            if isinstance(diff, (int, float)):
                event_diff.append(diff)
        base_delta = [x["delta_bps"] for x in baseline[h] if isinstance(x["delta_bps"], (int, float))]
        base_binance = [x["binance_bps"] for x in baseline[h] if isinstance(x["binance_bps"], (int, float))]
        report["event_outcomes"][key] = {
            "delta_directional_followthrough": summarize(event_delta),
            "binance_directional_return": summarize(event_binance),
            "binance_minus_delta_return_differential": summarize(event_diff),
        }
        report["matched_non_event_baseline"][key] = {
            "delta_raw_return": summarize(base_delta),
            "binance_raw_return": summarize(base_binance),
            "sampling": "non-overlapping anchors; direction-neutral baseline",
        }
    out = Path(args.output) if args.output else base / f"cross_venue_event_study_{args.session}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
