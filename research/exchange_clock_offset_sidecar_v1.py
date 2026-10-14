"""Passive exchange-clock offset sidecar; research telemetry only.

Never rewrites receive timestamps or exchange payloads. No order/trading APIs.
"""
import argparse, asyncio, json, math, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[1]
DEFAULT_OUT=ROOT/"data/processed/exchange_clock_offset_sidecar_v1.jsonl"
DEFAULT_ENDPOINTS={
    "binance":"https://api.binance.com/api/v3/time",
    "delta_india":"https://api.india.delta.exchange/v2/tickers/BTCUSD",
}


def parse_server_epoch_ms(payload):
    """Parse documented-style server time fields without guessing event timestamps."""
    if not isinstance(payload,dict): return None
    candidates=[]
    def visit(obj,key=""):
        if isinstance(obj,dict):
            for k,v in obj.items():
                lk=str(k).lower()
                if lk in {"servertime","server_time","servertimems","server_time_ms"}:
                    if isinstance(v,(int,float)) and math.isfinite(v):
                        candidates.append((lk,float(v)))
                elif lk in {"result","data"}:
                    visit(v,lk)
    visit(payload)
    if not candidates: return None
    # Prefer explicitly server-time-labelled fields, otherwise a timestamp-like value.
    candidates.sort(key=lambda x:(0 if "server" in x[0] else 1, -x[1]))
    value=candidates[0][1]
    if value>1e14: value/=1e3  # microseconds -> milliseconds
    elif value<1e11: value*=1000  # seconds -> milliseconds
    return value if value>0 else None


def sample_endpoint(name,url,timeout=5.0):
    send_epoch_ns=time.time_ns(); send_mono_ns=time.monotonic_ns()
    req=Request(url,headers={"User-Agent":"btc-fisher-research-clock/1.0","Accept":"application/json"})
    try:
        with urlopen(req,timeout=timeout) as response:
            body=response.read(65536)
            date_header=response.headers.get("Date")
        recv_mono_ns=time.monotonic_ns(); recv_epoch_ns=time.time_ns()
        payload=json.loads(body.decode("utf-8"))
        # HTTP Date is edge/proxy telemetry, not matching-engine time. Preserve it
        # for diagnostics only; never use it to estimate engine clock offset.
        server_ms=parse_server_epoch_ms(payload)
        time_source="explicit_server_time_field" if server_ms is not None else None
        rtt_ms=(recv_mono_ns-send_mono_ns)/1e6
        midpoint_epoch_ms=(send_epoch_ns+recv_epoch_ns)/2e6
        return {"exchange":name,"endpoint":url,"sample_status":"OK" if server_ms is not None else "UNPARSEABLE_SERVER_TIME",
            "sampled_at_utc":datetime.now(timezone.utc).isoformat(),
            "request_send_epoch_ns":send_epoch_ns,"response_receive_epoch_ns":recv_epoch_ns,
            "request_send_mono_ns":send_mono_ns,"response_receive_mono_ns":recv_mono_ns,
            "server_time_ms":server_ms,"server_time_source":time_source,"http_date_header":date_header,
            "rtt_ms":rtt_ms,
            "estimated_server_minus_local_offset_ms":server_ms-midpoint_epoch_ms if server_ms is not None else None,
            "offset_uncertainty_floor_ms":rtt_ms/2 if time_source=="explicit_server_time_field" else None,
            "http_date_used_for_engine_sync":False,
            "raw_receive_timestamps_modified":False,"real_orders":False}
    except Exception as exc:
        recv_mono_ns=time.monotonic_ns()
        return {"exchange":name,"endpoint":url,"sample_status":"ERROR",
            "sampled_at_utc":datetime.now(timezone.utc).isoformat(),
            "request_send_epoch_ns":send_epoch_ns,"request_send_mono_ns":send_mono_ns,
            "response_receive_mono_ns":recv_mono_ns,
            "rtt_ms":(recv_mono_ns-send_mono_ns)/1e6,
            "error":type(exc).__name__+": "+str(exc)[:200],
            "raw_receive_timestamps_modified":False,"real_orders":False}


async def run(out_path,interval_s=900.0,runtime_s=None,endpoints=None):
    endpoints=endpoints or DEFAULT_ENDPOINTS
    out_path.parent.mkdir(parents=True,exist_ok=True)
    start=time.monotonic()
    with out_path.open("a",encoding="utf-8") as fh:
        while runtime_s is None or time.monotonic()-start<runtime_s:
            for name,url in endpoints.items():
                row=await asyncio.to_thread(sample_endpoint,name,url)
                fh.write(json.dumps(row,separators=(",",":"),allow_nan=False)+"\n")
                fh.flush()
                print(json.dumps({"exchange":name,"status":row["sample_status"],"rtt_ms":row.get("rtt_ms"),
                    "offset_ms":row.get("estimated_server_minus_local_offset_ms"),"real_orders":False}),flush=True)
            if runtime_s is not None and time.monotonic()-start>=runtime_s: break
            await asyncio.sleep(max(1.0,interval_s))


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--output",default=str(DEFAULT_OUT))
    ap.add_argument("--interval",type=float,default=900.0)
    ap.add_argument("--runtime",type=float,default=None)
    ap.add_argument("--binance-url",default=DEFAULT_ENDPOINTS["binance"])
    ap.add_argument("--delta-url",default=DEFAULT_ENDPOINTS["delta_india"])
    a=ap.parse_args()
    asyncio.run(run(Path(a.output),a.interval,a.runtime,{"binance":a.binance_url,"delta_india":a.delta_url}))
if __name__=="__main__": main()
