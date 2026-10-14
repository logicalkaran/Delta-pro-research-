"""Read-only provenance/coverage audit for flow-L5 validation inputs."""
from __future__ import annotations
import collections, hashlib, json, math, statistics
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCES={
 "labelled_features":ROOT/"data/processed/live_microstructure_labeled_v2.jsonl",
 "l2_snapshots":ROOT/"data/processed/ofi_l2_snapshots_v2.jsonl",
}
OUT=ROOT/"data/processed/quant_protocol_data_audit_v1.json"

def utc(ts): return datetime.fromtimestamp(ts,timezone.utc).isoformat()

def load(path):
 rows=[]; bad=0
 with path.open(encoding="utf-8") as f:
  for line in f:
   try:
    r=json.loads(line); ts=float(r.get("ts",0))
    if not math.isfinite(ts) or ts<=0: bad+=1; continue
    r["_audit_ts"]=ts; rows.append(r)
   except (ValueError,TypeError,json.JSONDecodeError): bad+=1
 return rows,bad

def summarize(path):
 rows,bad=load(path); ts=sorted(r["_audit_ts"] for r in rows)
 gaps=[b-a for a,b in zip(ts,ts[1:])]
 return {"path":str(path.relative_to(ROOT)),"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
  "bytes":path.stat().st_size,"valid_rows":len(rows),"invalid_rows":bad,
  "timestamp_range_utc":[utc(ts[0]),utc(ts[-1])] if ts else None,
  "timestamp_range_epoch":[ts[0],ts[-1]] if ts else None,
  "duplicate_timestamps":len(ts)-len(set(ts)),
  "gap_seconds":{"median":statistics.median(gaps) if gaps else None,
   "p95":sorted(gaps)[int(.95*(len(gaps)-1))] if gaps else None,
   "max":max(gaps) if gaps else None},
  "rows":rows}

def run():
 summaries={k:summarize(p) for k,p in SOURCES.items()}
 a=summaries["labelled_features"]; b=summaries["l2_snapshots"]
 ar,br=a.pop("rows"),b.pop("rows")
 lo=max(a["timestamp_range_epoch"][0],b["timestamp_range_epoch"][0])
 hi=min(a["timestamp_range_epoch"][1],b["timestamp_range_epoch"][1])
 sessions=collections.defaultdict(list)
 for r in br: sessions[str(r.get("session_id","MISSING"))].append(r["_audit_ts"])
 session_stats=[]
 for sid,values in sorted(sessions.items()):
  values=sorted(values); gaps=[y-x for x,y in zip(values,values[1:])]
  session_stats.append({"session_id":sid,"rows":len(values),"duration_seconds":values[-1]-values[0],
    "median_gap_seconds":statistics.median(gaps) if gaps else None,
    "p95_gap_seconds":sorted(gaps)[int(.95*(len(gaps)-1))] if gaps else None,
    "duplicate_timestamps":len(values)-len(set(values))})
 status=collections.Counter(str(r.get("ofi_status","MISSING")) for r in br)
 kind=collections.Counter(str(r.get("timestamp_kind","MISSING")) for r in br)
 result={"audit":"QUANT_PROTOCOL_DATA_AUDIT_V1","created_at_utc":datetime.now(timezone.utc).isoformat(),
  "sources":summaries,"overlap":{"overlap_seconds":max(0,hi-lo),
    "timestamps_overlap":hi>=lo,"labelled_features_end_utc":a["timestamp_range_utc"][1],
    "l2_snapshots_start_utc":b["timestamp_range_utc"][0],
    "gap_between_windows_seconds":max(0,b["timestamp_range_epoch"][0]-a["timestamp_range_epoch"][1])},
  "labelled_features":{"rows_missing_session_id":sum(not r.get("session_id") for r in ar),
    "rows_with_session_id":sum(bool(r.get("session_id")) for r in ar),
    "median_freshness_seconds":statistics.median(float(r.get("fresh",999)) for r in ar) if ar else None},
  "l2_snapshot_sessions":session_stats,
  "l2_snapshot_semantics":{"ofi_status_counts":dict(status),"timestamp_kind_counts":dict(kind),
    "sampled_state_delta_rows":status.get("SAMPLED_STATE_DELTA_NOT_EXCHANGE_EVENT_OFI",0),
    "exchange_event_ofi_confirmed":False,
    "interpretation":"Most records are local state refreshes, not exchange-native order-book events. The computed state deltas must not be presented as validated event-level OFI."},
  "decision":{"historical_join":"BLOCKED_NO_TIME_OVERLAP",
    "flow_plus_l2_confirmatory_test":"BLOCKED",
    "reason":"The saved labelled feature window and saved L2 snapshot window do not overlap; most labelled rows also lack session_id. No nearest-time join across disjoint sessions is allowed.",
    "next_data_requirement":"Collect flow features and L5 price/size levels in the same prospective session with stable session IDs, exchange/receive timestamps, sequence/quality fields, and independently validated trade-side semantics."},
  "policy":{"read_only":True,"production_strategy_changed":False,"risk_limits_changed":False,"real_orders":False}}
 tmp=OUT.with_suffix(".json.tmp"); tmp.write_text(json.dumps(result,indent=2,allow_nan=False)); tmp.replace(OUT)
 print(json.dumps({"output":str(OUT),"sources":{k:{"valid_rows":v["valid_rows"],"range":v["timestamp_range_utc"],"sha256":v["sha256"]} for k,v in summaries.items()},
  "overlap":result["overlap"],"missing_session_id":result["labelled_features"]["rows_missing_session_id"],
  "l2_ofi_status_counts":dict(status),"decision":result["decision"],"real_orders":False},indent=2))
if __name__=="__main__": run()
