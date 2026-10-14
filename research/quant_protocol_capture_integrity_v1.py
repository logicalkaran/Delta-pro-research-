"""Offline integrity audit for bounded Delta raw gzip JSONL sessions."""
import argparse, collections, glob, gzip, hashlib, json, os
from delta_collector.orderbook_engine_v1 import OrderBookEngine, process_message

def audit(paths):
    result={"schema":"quant_protocol_capture_integrity_v1","inputs":paths,"files":[],
      "message_types":{},"orderbook":{"seen":0,"reconstructed":0,"checksum_ok":0,
      "checksum_failed":0,"sequence_or_reconstruction_errors":0,"snapshots":0,"updates":0,
      "first_sequence":None,"last_sequence":None},"malformed_json":0}
    types=collections.Counter(); failures=[]; engine=None; active_session=None
    for path in paths:
        session=os.path.dirname(path)
        if session != active_session:
            engine=OrderBookEngine(); active_session=session
        stats={"path":path,"compressed_bytes":os.path.getsize(path),
          "sha256":hashlib.sha256(open(path,"rb").read()).hexdigest(),"json_rows":0}
        with gzip.open(path,"rt",encoding="utf-8") as f:
            for line_no,line in enumerate(f,1):
                try: row=json.loads(line)
                except json.JSONDecodeError:
                    result["malformed_json"]+=1
                    if len(failures)<20: failures.append({"path":path,"line":line_no,"error":"invalid_json"})
                    continue
                stats["json_rows"]+=1
                m=row.get("message") or {}; typ=m.get("type","unknown"); types[typ]+=1
                if typ!="ob_updates": continue
                ob=result["orderbook"]; ob["seen"]+=1
                if m.get("action")=="snapshot": ob["snapshots"]+=1
                elif m.get("action")=="update": ob["updates"]+=1
                try:
                    process_message(engine,m); ob["reconstructed"]+=1
                    expected=int(m["cs"]); actual=engine.checksum()
                    if expected==actual: ob["checksum_ok"]+=1
                    else:
                        ob["checksum_failed"]+=1
                        if len(failures)<20: failures.append({"path":path,"line":line_no,"seq":m.get("seq"),"expected_checksum":expected,"actual_checksum":actual})
                    if ob["first_sequence"] is None: ob["first_sequence"]=m.get("seq")
                    ob["last_sequence"]=m.get("seq")
                except Exception as exc:
                    ob["sequence_or_reconstruction_errors"]+=1
                    if len(failures)<20: failures.append({"path":path,"line":line_no,"seq":m.get("seq"),"error":str(exc)[:200]})
        stats["orderbook_final_sequence"]=engine.last_seq
        stats["final_bid_levels"]=len(engine.bids); stats["final_ask_levels"]=len(engine.asks)
        result["files"].append(stats)
    result["message_types"]=dict(types)
    ob=result["orderbook"]; result["checksum_match_rate"]=ob["checksum_ok"]/ob["seen"] if ob["seen"] else None
    result["failures"]=failures
    result["status"]="PASS" if ob["seen"] and ob["checksum_ok"]==ob["seen"] and not ob["sequence_or_reconstruction_errors"] and not result["malformed_json"] else "FAIL_OR_INCOMPLETE"
    result["limitations"]=["Checks book reconstruction and checksums within each session.",
      "Does not prove no events were lost before the first snapshot or across reconnects.",
      "Does not establish predictive value or authorize live trading."]
    return result

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("paths",nargs="*")
    ap.add_argument("--output",default="data/processed/quant_protocol_capture_integrity_v1.json"); args=ap.parse_args()
    paths=args.paths or sorted(glob.glob("data/raw/quant_protocol_bounded/**/*_raw/**/*.jsonl.gz",recursive=True))
    if not paths: raise SystemExit("No bounded raw gzip JSONL files found")
    result=audit(paths); os.makedirs(os.path.dirname(args.output) or ".",exist_ok=True)
    with open(args.output,"w",encoding="utf-8") as f: json.dump(result,f,indent=2); f.write("\n")
    print(json.dumps({k:v for k,v in result.items() if k not in ("files","failures","inputs")},indent=2))
    print("output:",args.output)
if __name__=="__main__": main()
