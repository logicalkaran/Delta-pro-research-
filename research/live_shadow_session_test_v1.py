"""Time-boxed live market shadow test. Public GETs only; never places orders.

Consumes the already-running Delta collector, tails its bounded raw JSONL for
quality counters, compares local L1 with public REST L2 snapshots, measures
collector resources and runs the existing paper portfolio to separate output.
"""
from __future__ import annotations
import argparse, json, os, time, urllib.request, subprocess, threading, traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/delta_btc_raw.jsonl"
STATE = ROOT / "data/live_market_state.json"
OUTDIR = ROOT / "data/processed"
URL = "https://api.india.delta.exchange/v2/l2orderbook/BTCUSD"


def read_json(path):
    try: return json.loads(path.read_text(encoding="utf-8"))
    except Exception: return {}


def resource_snapshot(pid):
    out = {"pid": pid, "rss_kb": None, "cpu_ticks": None, "system_mem_available_kb": None}
    try:
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("VmRSS:"): out["rss_kb"] = int(line.split()[1])
        stat = Path(f"/proc/{pid}/stat").read_text().split()
        out["cpu_ticks"] = int(stat[13]) + int(stat[14])
    except Exception: pass
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"): out["system_mem_available_kb"] = int(line.split()[1]); break
    except Exception: pass
    return out


def get_snapshot():
    start = time.perf_counter()
    req = urllib.request.Request(URL, headers={"User-Agent": "btc-shadow-session-research/1.0"})
    with urllib.request.urlopen(req, timeout=4) as response:
        body = json.loads(response.read().decode("utf-8"))
        elapsed_ms = (time.perf_counter() - start) * 1000
        if response.status != 200 or body.get("success") is not True:
            raise RuntimeError("public snapshot endpoint returned unsuccessful response")
    result = body.get("result") or {}
    bids, asks = result.get("buy") or [], result.get("sell") or []
    if not bids or not asks: raise RuntimeError("snapshot has no two-sided book")
    return {"rtt_ms": round(elapsed_ms, 3), "exchange_updated_at": result.get("last_updated_at"),
            "bid": float(bids[0]["price"]), "ask": float(asks[0]["price"]),
            "bid_depth5": sum(float(x.get("size", 0)) for x in bids[:5]),
            "ask_depth5": sum(float(x.get("size", 0)) for x in asks[:5])}


def run(seconds=180, interval=10):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    OUTDIR.mkdir(parents=True, exist_ok=True)
    shadow_log = OUTDIR / f"live_shadow_portfolio_session_{stamp}.jsonl"
    shadow_summary = OUTDIR / f"live_shadow_portfolio_session_{stamp}_summary.json"
    report_path = OUTDIR / f"live_shadow_session_test_{stamp}.json"
    collector_pids = []
    try:
        raw = subprocess.check_output(["pgrep", "-f", "^python -m delta_collector.websocket_client$"], text=True).split()
        collector_pids = [int(x) for x in raw]
    except Exception: pass
    collector_pid = collector_pids[0] if collector_pids else None
    portfolio = {"started": False, "error": None}
    import sys
    sys.path.insert(0, str(ROOT))
    import paper.scalper_shadow_portfolio_v1 as shadow_module
    def shadow_worker():
        try:
            p = shadow_module
            p.OUT = shadow_log
            p.SUMMARY = shadow_summary
            p.main(seconds)
            portfolio["started"] = True
        except Exception as e:
            portfolio["error"] = f"{type(e).__name__}: {e}"
            portfolio["traceback"] = traceback.format_exc(limit=4)
    thread = threading.Thread(target=shadow_worker, name="paper-shadow", daemon=True)
    thread.start()
    started = time.time()
    raw_offset = RAW.stat().st_size if RAW.exists() else 0
    last_mtime = STATE.stat().st_mtime if STATE.exists() else 0
    last_change = time.monotonic()
    report = {"started_at_utc": datetime.now(timezone.utc).isoformat(), "requested_seconds": seconds,
              "mode": "LIVE_SHADOW_PUBLIC_DATA_ONLY", "real_orders": False,
              "private_api_calls": False, "collector_pid": collector_pid,
              "shadow_log": str(shadow_log.relative_to(ROOT)), "observations": [],
              "feed": {"raw_lines": 0, "trade_events": 0, "l1_events": 0, "l2_events": 0,
                       "parse_errors": 0, "file_truncations": 0, "max_received_gap_s": 0.0},
              "status": "RUNNING"}
    previous_received = None
    last_sample = 0
    try:
        while time.time() - started < seconds:
            now = time.time()
            # Watch the existing collector's bounded JSONL without modifying it.
            try:
                size = RAW.stat().st_size
                if size < raw_offset:
                    report["feed"]["file_truncations"] += 1
                    raw_offset = 0
                with RAW.open("rb") as fh:
                    fh.seek(raw_offset)
                    chunk = fh.read()
                    raw_offset = fh.tell()
                for line in chunk.splitlines():
                    try:
                        record = json.loads(line.decode("utf-8"))
                        msg = record.get("message", {})
                        typ = msg.get("type")
                        report["feed"]["raw_lines"] += 1
                        if typ == "trades": report["feed"]["trade_events"] += 1
                        elif typ == "ob_l1": report["feed"]["l1_events"] += 1
                        elif typ == "ob_l2": report["feed"]["l2_events"] += 1
                        received = record.get("received_at")
                        if received:
                            ts = datetime.fromisoformat(received).timestamp()
                            if previous_received is not None:
                                report["feed"]["max_received_gap_s"] = max(report["feed"]["max_received_gap_s"], ts-previous_received)
                            previous_received = ts
                    except Exception: report["feed"]["parse_errors"] += 1
            except Exception: pass
            try:
                st = STATE.stat().st_mtime
                if st > last_mtime:
                    last_mtime = st; last_change = time.monotonic()
            except Exception: pass
            if now - last_sample >= interval:
                obs = {"elapsed_s": round(now-started, 2), "local_state_age_s": None,
                       "local_bid": None, "local_ask": None, "snapshot": None,
                       "snapshot_error": None, "collector": resource_snapshot(collector_pid) if collector_pid else None,
                       "state_file_idle_s": round(time.monotonic()-last_change, 3)}
                state = read_json(STATE)
                if state:
                    obs["local_state_age_s"] = round(max(0, now-float(state.get("updated_at", now))), 3)
                    obs["local_bid"] = float(state.get("best_bid") or 0)
                    obs["local_ask"] = float(state.get("best_ask") or 0)
                try:
                    snap = get_snapshot()
                    if obs["local_bid"] and obs["local_ask"]:
                        snap["bid_diff_ticks"] = round((obs["local_bid"]-snap["bid"])/0.5, 2)
                        snap["ask_diff_ticks"] = round((obs["local_ask"]-snap["ask"])/0.5, 2)
                        snap["local_spread_bps"] = round((obs["local_ask"]-obs["local_bid"])/max((obs["local_ask"]+obs["local_bid"])/2,1)*10000, 4)
                    obs["snapshot"] = snap
                except Exception as e: obs["snapshot_error"] = f"{type(e).__name__}: {e}"
                report["observations"].append(obs); last_sample = now
            time.sleep(0.20)
    except KeyboardInterrupt:
        report["status"] = "INTERRUPTED"
    finally:
        thread.join(timeout=3)
    duration = time.time()-started
    samples = report["observations"]
    rtts = sorted(o["snapshot"]["rtt_ms"] for o in samples if o.get("snapshot"))
    def percentile(arr, p):
        if not arr: return None
        return round(arr[min(len(arr)-1, int((len(arr)-1)*p))], 3)
    drifts = [max(abs(o["snapshot"].get("bid_diff_ticks", 0)), abs(o["snapshot"].get("ask_diff_ticks", 0)))
              for o in samples if o.get("snapshot") and "bid_diff_ticks" in o["snapshot"]]
    report["duration_s"] = round(duration, 2)
    report["summary"] = {"snapshot_successes": sum(bool(o.get("snapshot")) for o in samples),
        "snapshot_failures": sum(bool(o.get("snapshot_error")) for o in samples),
        "public_rest_rtt_p50_ms": percentile(rtts, .50), "public_rest_rtt_p95_ms": percentile(rtts, .95),
        "max_best_quote_difference_ticks": max(drifts) if drifts else None,
        "local_state_stale_samples_gt_2s": sum(o.get("local_state_age_s") is not None and o["local_state_age_s"] > 2 for o in samples),
        "max_state_file_idle_s": max((o.get("state_file_idle_s", 0) for o in samples), default=None),
        "collector_rss_peak_kb": max((o["collector"]["rss_kb"] for o in samples if o.get("collector") and o["collector"].get("rss_kb") is not None), default=None),
        "collector_cpu_ticks_delta": (samples[-1]["collector"]["cpu_ticks"]-samples[0]["collector"]["cpu_ticks"] if len(samples)>1 and samples[0].get("collector") and samples[-1].get("collector") and samples[0]["collector"].get("cpu_ticks") is not None and samples[-1]["collector"].get("cpu_ticks") is not None else None),
        "shadow_log_bytes": shadow_log.stat().st_size if shadow_log.exists() else 0,
        "shadow_summary_exists": shadow_summary.exists(), "shadow_thread_error": portfolio["error"]}
    if report["status"] != "INTERRUPTED":
        report["status"] = "COMPLETED_SHADOW_ONLY"
    report["shadow_summary"] = str(shadow_summary.relative_to(ROOT)) if shadow_summary.exists() else None
    report["decision"] = "REVIEW_REQUIRED_NO_LIVE_EXECUTION"
    report["limitations"] = ["REST snapshots are sampled, not an exchange-authoritative replay of every WebSocket event",
        "quote differences can be caused by snapshot timing as well as packet loss", "shadow fill and queue models are approximate",
        "no private API acknowledgement latency measured because no orders were sent", "Qwen was not run in the critical path"]
    report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(report_path.relative_to(ROOT)), "shadow_log": str(shadow_log.relative_to(ROOT)),
        "status": report["status"], "duration_s": report["duration_s"], "feed": report["feed"],
        "summary": report["summary"], "portfolio_summary": str(shadow_summary.relative_to(ROOT)) if shadow_summary.exists() else None,
        "decision": report["decision"]}, indent=2), flush=True)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=int, default=180)
    ap.add_argument("--interval", type=float, default=10)
    args = ap.parse_args()
    run(max(30, min(args.seconds, 900)), max(5, args.interval))
