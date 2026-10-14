"""Sampled-path event exit study; research only, never used by runtime."""
from __future__ import annotations

import json
import math
import statistics
import sys
from bisect import bisect_left
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from execution.fill_simulator import FillModel, simulate
from research.event_move_cost_break_even_v1 import (
    EVENT_TYPES, HORIZONS, MIN_SAMPLE, chronological_split, event_flags,
    load_rows, num, purge_training_rows, thresholds,
)

LAB = ROOT / "data/processed/live_microstructure_labeled_v1.jsonl"
TAPE = ROOT / "data/processed/live_microstructure_features_v1.jsonl"
RAW = ROOT / "data/raw"
OUT = ROOT / "data/processed/path_aware_event_exit_study_v1.json"
DELAYS = (0, 1, 2, 5)
MODEL = FillModel()


def read_jsonl(path):
    rows, bad = [], 0
    if path.exists():
        with path.open(errors="replace") as stream:
            for line in stream:
                try:
                    value = json.loads(line)
                    if isinstance(value, dict):
                        rows.append(value)
                    else:
                        bad += 1
                except (json.JSONDecodeError, TypeError):
                    bad += 1
    return rows, bad


def audit_rows(rows):
    source_ts = [num(x.get("ts")) for x in rows]
    ts = sorted(x for x in source_ts if x is not None)
    gaps = [b-a for a, b in zip(ts, ts[1:])]
    return {
        "row_count": len(rows), "valid_timestamp_count": len(ts),
        "missing_timestamp_count": len(rows)-len(ts),
        "start_ts": ts[0] if ts else None, "end_ts": ts[-1] if ts else None,
        "duration_seconds": ts[-1]-ts[0] if ts else None,
        "duplicate_timestamp_rows": len(ts)-len(set(ts)),
        "out_of_order_adjacent_pairs": sum(a is not None and b is not None and a>b for a,b in zip(source_ts,source_ts[1:])),
        "gap_seconds": {"count": len(gaps), "median": statistics.median(gaps) if gaps else None,
                        "max": max(gaps) if gaps else None,
                        "over_2_seconds": sum(x>2 for x in gaps), "over_5_seconds": sum(x>5 for x in gaps)},
    }


def raw_inventory(labeled_start, labeled_end):
    inventory=[]
    for path in sorted(RAW.rglob("*.jsonl")):
        rows,bad=read_jsonl(path)
        times=[]; price_rows=0; kinds=Counter(); field_union=set()
        for row in rows:
            message=row.get("message", row)
            if not isinstance(message,dict): continue
            field_union.update(message)
            kind=message.get("type")
            kinds[str(kind)]+=1
            t=message.get("ts",message.get("timestamp"))
            try:
                t=float(t)
                if t>1e14:t/=1e6
                if math.isfinite(t):times.append(t)
            except (TypeError,ValueError):pass
            if any(k in message for k in ("mid","mid_price","price","p","bp","ap")):price_rows+=1
        ordered=sorted(times); lo=ordered[0] if ordered else None; hi=ordered[-1] if ordered else None
        gaps=[b-a for a,b in zip(ordered,ordered[1:])]
        inventory.append({"file":str(path.relative_to(ROOT)),"rows":len(rows),"invalid_json_rows":bad,
            "timestamp_start":lo,"timestamp_end":hi,"timestamped_rows":len(times),"price_field_rows":price_rows,
            "gap_seconds":{"count":len(gaps),"median":statistics.median(gaps) if gaps else None,
                "max":max(gaps) if gaps else None,"over_2_seconds":sum(g>2 for g in gaps),"over_5_seconds":sum(g>5 for g in gaps)},
            "types":dict(kinds),"message_fields":sorted(field_union),
            "overlaps_labeled_capture":bool(lo is not None and lo<=labeled_end and hi>=labeled_start)})
    return inventory


def nearest_index(times, target, start=0):
    i=bisect_left(times,target,lo=start)
    return i if i<len(times) else None


def select_nonoverlapping(candidates, horizon, max_delay=max(DELAYS)):
    """Select event intervals conservatively across every tested entry delay."""
    selected=[]; last_end=-math.inf
    for ts,row in sorted(candidates,key=lambda x:x[0]):
        if ts>=last_end:
            selected.append((ts,row))
            last_end=ts+horizon+max_delay
    return selected


def path_metrics(tape, times, start_ts, entry_mid, side, horizon, delay, target_bps, stop_bps, window_end=None):
    entry_i=nearest_index(times,start_ts+delay)
    if entry_i is None or (window_end is not None and times[entry_i]>window_end):return None
    entry=tape[entry_i][1]
    exit_i=nearest_index(times,times[entry_i]+horizon,entry_i+1)
    if exit_i is None or (window_end is not None and times[exit_i]>window_end):return None
    end=exit_i+1
    favorable=[]; adverse=[]; touch=None
    for ts,mid in tape[entry_i+1:end]:
        move=side*(mid/entry-1)*10000
        favorable.append(move); adverse.append(move)
        if touch is None:
            if move>=target_bps:touch={"kind":"target","ts":ts,"move_bps":move}
            elif move<=-stop_bps:touch={"kind":"stop","ts":ts,"move_bps":move}
    # Include zero at entry; sampled prices only, without intrabar interpolation.
    all_moves=[0.0]+favorable
    observed_delay=times[entry_i]-start_ts
    return {"entry_ts":times[entry_i],"entry_delay_observed_seconds":observed_delay,
        "entry_mid":entry,"exit_ts":times[exit_i],"exit_delay_from_entry_seconds":times[exit_i]-times[entry_i],
        "net_directional_endpoint_bps":side*(tape[exit_i][1]/entry-1)*10000,
        "mfe_bps":max(all_moves),"mae_bps":min(all_moves),
        "first_target_or_stop_touch":touch,"sample_count":exit_i-entry_i+1}


def summarize(records, route, target_bps, stop_bps):
    cost=simulate(0,route,MODEL).total_cost_bps
    endpoint=[r["net_directional_endpoint_bps"] for r in records]
    mfes=[r["mfe_bps"] for r in records]; maes=[r["mae_bps"] for r in records]
    touches=Counter((r["first_target_or_stop_touch"] or {}).get("kind","neither_sampled") for r in records)
    net=[x-cost for x in endpoint]
    return {"sample_count":len(records),"full_round_trip_cost_bps":cost,
        "gross_endpoint_mean_bps":statistics.fmean(endpoint) if endpoint else None,
        "net_endpoint_mean_after_full_cost_bps":statistics.fmean(net) if net else None,
        "endpoint_positive_rate":sum(x>0 for x in endpoint)/len(endpoint) if endpoint else None,
        "mfe_mean_bps":statistics.fmean(mfes) if mfes else None,"mfe_median_bps":statistics.median(mfes) if mfes else None,
        "mae_mean_bps":statistics.fmean(maes) if maes else None,"mae_median_bps":statistics.median(maes) if maes else None,
        "target_bps":target_bps,"stop_bps":stop_bps,"first_touch_counts":dict(touches),
        "touch_rule":"first sampled mid reaching +target_bps or -stop_bps from delayed entry; ties resolved by observation order; no interpolation"}


def build_report():
    labeled=load_rows(LAB)
    features,_=read_jsonl(TAPE)
    # Use observed feature-tape mid snapshots as the path; do not synthesize prices.
    raw_tape=sorted(((num(r.get("ts")),num(r.get("mid"))) for r in features),key=lambda p:p[0] if p[0] is not None else -math.inf)
    tape=[(t,p) for t,p in raw_tape if t is not None and p is not None and p>0]
    times=[x[0] for x in tape]
    train,holdout,holdout_start=chronological_split(labeled)
    threshold_train=purge_training_rows(train,holdout_start,max(HORIZONS))
    q=thresholds(threshold_train)
    lab_ts=[num(r.get("ts")) for r in labeled if num(r.get("ts")) is not None]
    labeled_start=min(lab_ts) if lab_ts else None
    labeled_end=max(lab_ts) if lab_ts else None
    tested_window_end=labeled_end+max(HORIZONS)+max(DELAYS) if lab_ts else None
    tested_window_features=[r for r in features if (num(r.get("ts")) is not None and labeled_start<=num(r.get("ts"))<=tested_window_end)] if lab_ts else []
    tested_window_tape=[(t,p) for t,p in tape if labeled_start<=t<=tested_window_end] if lab_ts else []
    tape_lookup={t for t in times}
    aligned=sum(t in tape_lookup for t in lab_ts)
    report={"schema":"path_aware_event_exit_study_v1","research_only":True,"real_orders":False,
        "source_files":[{"file":"data/processed/event_move_cost_break_even_v1.json","role":"current endpoint-only report inspected"},
            {"file":"data/processed/live_microstructure_labeled_v1.jsonl","role":"event features and forward horizon labels"},
            {"file":"data/processed/live_microstructure_features_v1.jsonl","role":"ordered sampled mid path tape"},
            {"file":"execution/fill_simulator.py","role":"full maker/taker costs"}],
        "raw_source_inventory":raw_inventory(min(lab_ts),max(lab_ts)),
        "capture_audit":{"labeled_rows":audit_rows(labeled),"feature_tape_full_capture":audit_rows(features),
            "tested_path_window":{"start_ts":labeled_start,"end_ts_inclusive":tested_window_end,
                "rule":"labeled start through labeled end + max horizon + max tested entry delay, inclusive",
                "feature_rows":audit_rows(tested_window_features),"valid_positive_mid_rows":len(tested_window_tape)},
            "path_reliability_gap_audit":"tested_path_window.feature_rows.gap_seconds",
            "valid_positive_mid_rows":len(tape),"exact_timestamp_alignment_rows":aligned,
            "labeled_timestamp_alignment_fraction":aligned/len(lab_ts) if lab_ts else None,
            "feature_rows_before_labeled_start":sum(t<min(lab_ts) for t in times) if lab_ts else 0,
            "feature_rows_after_labeled_end":sum(t>max(lab_ts) for t in times) if lab_ts else 0,
            "raw_feed_overlap":any(x["overlaps_labeled_capture"] for x in raw_inventory(min(lab_ts),max(lab_ts))) if lab_ts else False,
            "interpretation":"Raw venue JSONL captures do not overlap this labeled capture. The derived feature tape retains a timestamped mid at every labeled row (alignment counted above), making sampled paths reconstructable for aligned events; it is not a tick-complete path."},
        "method":{"split":"chronological first 60% train, final 40% holdout; report holdout only",
            "thresholds":"event thresholds fitted using first-60%-chronological training rows only, after excluding rows whose 300-second label crosses the holdout boundary","purge":"training rows whose endpoint label future_ts crosses the first holdout timestamp are excluded; threshold fit uses the conservative 300-second purge",
            "entry_selection":f"event flags on holdout feature rows; chronological non-overlap per event and horizon using conservative [event_ts,event_ts+horizon+{max(DELAYS)}s] intervals, covering all tested entry delays",
            "delays_seconds":list(DELAYS),"delay_entry":"for each delay, enter at first observed mid timestamp >= event timestamp + requested delay; exit at first observed sample >= entry timestamp + horizon",
            "mfe_mae":"directional excursion from delayed entry over observed mids through exit sample, including zero at entry",
            "touch_levels":"symmetric full taker round-trip cost from FillModel; first sampled crossing only",
            "sampling_limitations":"No extrema between snapshots are observable. Nearest-at-or-after entry and exit can extend requested delay/horizon; long gaps can hide touches and worsen true MFE/MAE. Full-capture and tested-path-window gap audits are reported separately; path reliability uses tested-window gaps."},
        "split":{"train_rows":len(train),"threshold_training_rows_after_300s_purge":len(threshold_train),"holdout_rows":len(holdout),"holdout_start_ts":holdout_start,"thresholds":q,
            "purged_training_rows_by_horizon":{str(h):len(train)-len(purge_training_rows(train,holdout_start,h)) for h in HORIZONS}},
        "costs":{"source":"execution/fill_simulator.py FillModel","taker_round_trip_bps":simulate(0,"TAKER",MODEL).total_cost_bps,
            "maker_round_trip_bps":simulate(0,"MAKER",MODEL).total_cost_bps,"maker_fill_probability":MODEL.maker_fill_probability,
            "maker_metrics_conditional_on_fill":True},"minimum_nonoverlap_n":MIN_SAMPLE,"results":[],
        "multiple_testing_caveat":"Exploratory screening across 40 event/horizon candidates, four entry delays and two cost routes; no multiplicity correction or independent replication. Eligibility at n>=30 is assessed for each event/horizon using zero-delay path availability; delayed estimates can have fewer complete paths.",
        "conclusion":"Descriptive sampled-mid path study only. Results cannot establish executable stops/targets because source data contain periodic snapshots rather than every price update; no latency-to-order or queue/fill path is recorded."}
    maker_cost=simulate(0,"MAKER",MODEL).total_cost_bps
    taker_cost=simulate(0,"TAKER",MODEL).total_cost_bps
    for h in HORIZONS:
      for event in EVENT_TYPES:
        side=1 if event.endswith("LONG") else -1
        candidates=[]
        for row in holdout:
            if event_flags(row,q).get(event,False):
                ts=num(row.get("ts"));
                if ts is not None:candidates.append((ts,row))
        selected=select_nonoverlapping(candidates,h)
        zero=[path_metrics(tape,times,ts,num(row.get("mid")),side,h,0,taker_cost,taker_cost,tested_window_end) for ts,row in selected]
        zero=[x for x in zero if x is not None]
        if len(zero)<MIN_SAMPLE:continue
        entry={"horizon_s":h,"event":event,"direction":"LONG" if side==1 else "SHORT",
            "raw_candidates":len(candidates),"nonoverlap_candidates":len(selected),"zero_delay_complete_paths":len(zero),"delays":[]}
        for delay in DELAYS:
            records=[path_metrics(tape,times,ts,num(row.get("mid")),side,h,delay,taker_cost,taker_cost,tested_window_end) for ts,row in selected]
            records=[x for x in records if x is not None]
            entry["delays"].append({"requested_delay_s":delay,"observed_entry_delay_seconds":{"median":statistics.median([x["entry_delay_observed_seconds"] for x in records]) if records else None,"max":max((x["entry_delay_observed_seconds"] for x in records),default=None)},
                "taker":summarize(records,"TAKER",taker_cost,taker_cost),"maker_conditional_on_fill":summarize(records,"MAKER",maker_cost,maker_cost)})
        report["results"].append(entry)
    report["eligible_event_horizon_count"]=len(report["results"])
    return report


def main():
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(build_report(),indent=2,sort_keys=True)+"\n")
    print(f"wrote {OUT}")

if __name__=="__main__":main()
