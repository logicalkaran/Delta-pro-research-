"""Capture synchronized microstructure + L5 snapshots from the local read-only state.
Research-only sidecar. Does not connect to exchange, mutate source state, or place orders.
"""
from __future__ import annotations
import argparse, hashlib, json, math, time, uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
STATE=ROOT/"data/live_microstructure_state.json"
OUTDIR=ROOT/"data/raw/quant_protocol_aligned"
MAX_SESSION_BYTES=20_000_000
POLL_SECONDS=.20
MAX_SOURCE_AGE_SECONDS=2.0

def finite(value):
    try:
        x=float(value)
        return x if math.isfinite(x) else None
    except (TypeError,ValueError):
        return None

def levels(value):
    result=[]
    if not isinstance(value,list): return result
    for item in value[:5]:
        if not isinstance(item,(list,tuple)) or len(item)<2: continue
        p,q=finite(item[0]),finite(item[1])
        if p is not None and q is not None and p>0 and q>=0:
            result.append([p,q])
    return result

def extract_snapshot(state, session_id, sequence, received_epoch=None):
    if received_epoch is None: received_epoch=time.time()
    ob=state.get("order_book") or {}; windows=state.get("windows") or {}
    quality=state.get("quality") or {}; price=state.get("price") or {}
    ts=finite(state.get("updated_at_epoch"))
    mid=finite(ob.get("mid_price")); bid=finite(ob.get("best_bid")); ask=finite(ob.get("best_ask"))
    age=finite(quality.get("fresh_seconds"))
    bids=levels(ob.get("bids_l5")); asks=levels(ob.get("asks_l5"))
    delta30=finite((windows.get("30") or {}).get("delta_pct"))
    imb5=finite(ob.get("imbalance_5"))
    flow=(windows.get("1") or {})
    buy=finite(flow.get("buy_volume")); sell=finite(flow.get("sell_volume"))
    row={"schema":"quant_protocol_aligned_capture_v1","session_id":session_id,
      "sequence":int(sequence),"symbol":str(state.get("symbol","BTCUSD")),
      "state_updated_epoch":ts,"received_epoch":float(received_epoch),
      "timestamp_kind":"local_state_refresh_not_exchange_book_event",
      "source_event_timestamp_present":False,"source_age_seconds":age,
      "mid":mid,"best_bid":bid,"best_ask":ask,
      "spread":(ask-bid) if ask is not None and bid is not None else None,
      "imb5":imb5,"delta30":delta30,
      "signed_flow_1s":(buy-sell) if buy is not None and sell is not None else None,
      "bids_l5":bids,"asks_l5":asks,
      "trade_samples":finite(quality.get("trade_samples")),
      "book_samples":finite(quality.get("book_samples")),
      "last_trade":state.get("last_trade"),
      "research_only":True,"real_orders":False}
    reasons=[]
    if ts is None or ts<=0: reasons.append("INVALID_STATE_TIMESTAMP")
    if mid is None or mid<=0 or bid is None or ask is None or bid<=0 or ask<bid: reasons.append("INVALID_TOP_OF_BOOK")
    if not bids or not asks: reasons.append("MISSING_L5_LEVELS")
    if age is None or age<0 or age>MAX_SOURCE_AGE_SECONDS: reasons.append("STALE_OR_UNKNOWN_SOURCE_AGE")
    if delta30 is None or imb5 is None: reasons.append("MISSING_FLOW_OR_IMBALANCE")
    row["quality_status"]="PASS" if not reasons else "REJECT"
    row["quality_reasons"]=reasons
    return row

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds",type=int,default=21600)
    parser.add_argument("--state",type=Path,default=STATE)
    parser.add_argument("--output-dir",type=Path,default=OUTDIR)
    parser.add_argument("--max-bytes",type=int,default=MAX_SESSION_BYTES)
    args=parser.parse_args()
    if args.seconds<1 or args.max_bytes<1024: parser.error("seconds >= 1 and max-bytes >= 1024 required")
    args.output_dir.mkdir(parents=True,exist_ok=True)
    sid="quant_l5_"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"_"+uuid.uuid4().hex[:6]
    out=args.output_dir/(sid+".jsonl")
    # Exclusive creation prevents accidental overwrite.
    with out.open("x",encoding="utf-8") as f:
        start=time.monotonic(); last_ts=None; seq=0; accepted=0; rejected=0; last_report=0
        while time.monotonic()-start < args.seconds:
            if args.state.exists():
                try:
                    state=json.loads(args.state.read_text(encoding="utf-8"))
                    ts=finite(state.get("updated_at_epoch"))
                    if ts is not None and ts!=last_ts:
                        row=extract_snapshot(state,sid,seq+1,time.time())
                        encoded=json.dumps(row,separators=(",",":"),allow_nan=False)+"\n"
                        if out.stat().st_size+len(encoded.encode())>args.max_bytes:
                            break
                        f.write(encoded); f.flush()
                        seq+=1; last_ts=ts
                        if row["quality_status"]=="PASS": accepted+=1
                        else: rejected+=1
                except (OSError,ValueError,TypeError):
                    pass
            time.sleep(POLL_SECONDS)
        f.flush()
    digest=hashlib.sha256(out.read_bytes()).hexdigest()
    report={"status":"CAPTURE_COMPLETE" if seq else "NO_NEW_SOURCE_STATE",
      "session_id":sid,"output":str(out.relative_to(ROOT)),"rows":seq,
      "quality_pass_rows":accepted,"quality_reject_rows":rejected,
      "bytes":out.stat().st_size,"sha256":digest,
      "source_state":str(args.state),"duration_requested_seconds":args.seconds,
      "timestamp_warning":"state_updated_epoch is local state-refresh time, not exchange-native event time",
      "research_only":True,"real_orders":False}
    print(json.dumps(report,indent=2))
    return 0 if seq else 2

if __name__=="__main__": raise SystemExit(main())
