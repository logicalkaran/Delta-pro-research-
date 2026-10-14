"""Bounded autonomous research supervisor for Delta BTCUSD. Research/paper only.

Starts the existing public feed and existing paper simulator, runs causal
prediction diagnostics, records health/evidence, and produces a promotion report.
It never generates executable code from an LLM, changes strategy/risk policy,
or submits/cancels exchange orders. LLMs may be added as advisory providers only.
"""
from __future__ import annotations
import argparse, json, os, signal, subprocess, sys, time, traceback
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "data/live_microstructure_state.json"
CANDLES = ROOT / "data/live_candles.json"
OUT = ROOT / "data/processed/autonomous_research_node_v1.json"
LOG = ROOT / "data/processed/autonomous_research_node_v1.jsonl"
KILL = ROOT / "data/run/LIVE_KILL_SWITCH"
POLICY = ROOT / "execution/LIVE_PROMOTION_POLICY.json"
PAPER_SUMMARY = ROOT / "data/processed/live_execution_paper_v3_summary.json"
PY = sys.executable
STOP = False


def _signal_stop(signum, frame):
    global STOP
    STOP = True

signal.signal(signal.SIGINT, _signal_stop)
signal.signal(signal.SIGTERM, _signal_stop)


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return default


def append_event(event: dict[str, Any]) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, separators=(",", ":"), allow_nan=False) + "\n")


def health_snapshot(now: float | None = None) -> dict[str, Any]:
    now = time.time() if now is None else now
    state = read_json(STATE, {})
    candle_rows = read_json(CANDLES, [])
    policy = read_json(POLICY, {})
    updated = state.get("updated_at_epoch")
    if updated is None:
        updated = state.get("timestamp", state.get("updated_at"))
    try:
        age = max(0.0, now - float(updated)) if updated is not None else None
    except (ValueError, TypeError):
        age = None
    quality = state.get("quality") or {}
    feed_age = quality.get("fresh_seconds")
    try:
        feed_age = float(feed_age) if feed_age is not None else None
    except (ValueError, TypeError):
        feed_age = None
    book = state.get("order_book") or {}
    valid_book = all(_positive(book.get(k)) for k in ("best_bid", "best_ask", "mid_price"))
    if valid_book:
        valid_book = float(book["best_bid"]) < float(book["best_ask"])
    blocked = KILL.exists()
    reasons = []
    if not state: reasons.append("STATE_MISSING")
    if age is None or age > 2.0: reasons.append("STATE_STALE_OR_UNTIMESTAMPED")
    if feed_age is None or feed_age > 0.5: reasons.append("FEED_EVENT_AGE_OVER_500MS")
    if not valid_book: reasons.append("INVALID_ORDER_BOOK")
    if not isinstance(candle_rows, list) or len(candle_rows) < 2: reasons.append("INSUFFICIENT_CANDLES")
    if policy.get("status") != "BLOCKED_UNTIL_VALIDATED": reasons.append("PROMOTION_POLICY_NOT_LOCKED")
    if blocked: reasons.append("LIVE_KILL_SWITCH_PRESENT")
    return {"timestamp": now, "state_file_age_s": age, "feed_event_age_s": feed_age,
            "book_valid": valid_book, "candle_count": len(candle_rows) if isinstance(candle_rows, list) else 0,
            "regime": state.get("regime"), "state": "HEALTHY" if not reasons else "HALT_FAIL_CLOSED",
            "reasons": reasons, "kill_switch_present": blocked,
            "real_orders": False, "policy_status": policy.get("status")}


def _positive(value) -> bool:
    try:
        x = float(value)
        return x > 0 and x < float("inf")
    except (ValueError, TypeError):
        return False


def generate_hypothesis_registry() -> dict[str, Any]:
    """Refresh the predeclared hypothesis registry; never generates executable code."""
    cmd = [PY, str(ROOT / "research/prediction_hypothesis_registry_v1.py")]
    try:
        p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=20)
        result = read_json(ROOT / "data/processed/prediction_hypothesis_registry_v1.json", {})
        return {"status": "COMPLETED" if p.returncode == 0 else "FAILED",
                "returncode": p.returncode, "hypothesis_count": len(result.get("hypotheses", [])),
                "registry_path": "data/processed/prediction_hypothesis_registry_v1.json",
                "stderr_tail": p.stderr[-1000:], "real_orders": False}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "FAILED", "error": type(exc).__name__, "detail": str(exc), "real_orders": False}


def run_prediction_diagnostics() -> dict[str, Any]:
    cmd = [PY, str(ROOT / "research/prediction_layer_v1.py")]
    try:
        p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=90)
        result = read_json(ROOT / "data/processed/prediction_layer_v1.json", {})
        return {"returncode": p.returncode, "status": "COMPLETED" if p.returncode == 0 else "FAILED",
                "output_path": "data/processed/prediction_layer_v1.json",
                "stderr_tail": p.stderr[-1500:], "result_status": result.get("status"),
                "source_candles": result.get("source_candles"), "labeled_rows": result.get("labeled_rows"),
                "walk_forward_status": {k: (v or {}).get("status") for k, v in (result.get("walk_forward") or {}).items()},
                "real_orders": False}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "FAILED", "error": type(exc).__name__, "detail": str(exc), "real_orders": False}


def evaluate_evidence() -> dict[str, Any]:
    policy = read_json(POLICY, {})
    summary = read_json(PAPER_SUMMARY, {})
    trades = int(summary.get("trades", 0) or 0)
    avg = summary.get("avg_net_bps")
    pf = summary.get("profit_factor")
    try: avg = float(avg) if avg is not None else None
    except (ValueError, TypeError): avg = None
    try: pf = float(pf) if pf is not None else None
    except (ValueError, TypeError): pf = None
    blockers = []
    if policy.get("status") != "BLOCKED_UNTIL_VALIDATED": blockers.append("POLICY_NOT_LOCKED")
    if summary.get("real_orders") is not False: blockers.append("PAPER_ONLY_INVARIANT_UNPROVEN")
    if trades < int(policy.get("minimum_labeled_trades", 100)): blockers.append("MINIMUM_100_TRADES_NOT_MET")
    if avg is None or avg <= 0: blockers.append("POSITIVE_NET_EXPECTANCY_NOT_MET")
    if pf is None or pf < float(policy.get("minimum_profit_factor", 1.2)): blockers.append("PROFIT_FACTOR_THRESHOLD_NOT_MET")
    return {"paper_trades": trades, "avg_net_bps": avg, "profit_factor": pf,
            "status": "EVIDENCE_PASSES_BASIC_THRESHOLDS" if not blockers else "INSUFFICIENT_OR_NEGATIVE_EVIDENCE",
            "blockers": blockers, "live_promotion": "BLOCKED_UNTIL_VALIDATED", "real_orders": False}


def _terminate(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None: return
    proc.terminate()
    try: proc.wait(timeout=4)
    except subprocess.TimeoutExpired:
        proc.kill(); proc.wait(timeout=2)


def run(seconds: int = 180, poll_seconds: float = 1.0, start_paper: bool = True) -> dict[str, Any]:
    if seconds < 1 or seconds > 86400: raise ValueError("seconds must be 1..86400")
    if poll_seconds < 0.5 or poll_seconds > 30: raise ValueError("poll_seconds must be 0.5..30")
    started = time.time()
    feed = paper = None
    events = []
    try:
        if KILL.exists():
            events.append({"event": "HALT", "reason": "LIVE_KILL_SWITCH_PRESENT"})
        else:
            feed = subprocess.Popen([PY, str(ROOT / "paper/live_shadow_feed_v1.py"), "--seconds", str(seconds)],
                                    cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            events.append({"event": "FEED_STARTED", "pid": feed.pid, "mode": "PUBLIC_READ_ONLY"})
            if start_paper:
                paper = subprocess.Popen([PY, str(ROOT / "paper/live_execution_paper_v3.py"), "--seconds", str(seconds)],
                                         cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                events.append({"event": "PAPER_STARTED", "pid": paper.pid, "mode": "SIMULATED_EXECUTION"})
            while not STOP and time.time() - started < seconds:
                h = health_snapshot()
                if h["state"] == "HALT_FAIL_CLOSED":
                    events.append({"event": "HEALTH_BLOCK", "health": h})
                    # Feed event age may be temporarily high during connection startup;
                    # stop research execution after 10s without a healthy feed.
                    if time.time() - started > 10 and (h["feed_event_age_s"] is None or h["feed_event_age_s"] > 0.5 or h["kill_switch_present"]):
                        _terminate(paper); paper = None
                else:
                    events.append({"event": "HEALTH", "health": h})
                if feed and feed.poll() is not None:
                    events.append({"event": "FEED_EXITED", "returncode": feed.returncode})
                    _terminate(paper); paper = None
                    break
                if KILL.exists():
                    events.append({"event": "HALT", "reason": "LIVE_KILL_SWITCH_PRESENT"})
                    _terminate(paper); paper = None
                    break
                time.sleep(poll_seconds)
    finally:
        _terminate(paper)
        _terminate(feed)
    registry = generate_hypothesis_registry()
    prediction = run_prediction_diagnostics()
    health = health_snapshot()
    report = {"version": "autonomous_research_node_v1", "created_at": time.time(),
              "duration_s": round(time.time() - started, 3), "status": "RESEARCH_COMPLETE",
              "health": health, "events_count": len(events), "events_tail": events[-30:],
              "hypothesis_generation": registry, "prediction_diagnostics": prediction, "paper_evidence": evaluate_evidence(),
              "hypothesis_registry": "data/processed/prediction_hypothesis_registry_v1.json",
              "constraints": {"real_orders": False, "automatic_code_execution": False,
                              "risk_policy_mutation": False, "production_strategy_mutation": False,
                              "automatic_promotion": False, "bounded_session": True}}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    for e in events: append_event(e)
    append_event({"event": "SESSION_REPORT", "status": report["status"], "health": health["state"],
                  "paper_evidence": report["paper_evidence"]["status"], "real_orders": False})
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seconds", type=int, default=180, help="bounded run duration (max 86400)")
    ap.add_argument("--poll-seconds", type=float, default=1.0)
    ap.add_argument("--no-paper", action="store_true", help="observe feed and run diagnostics without paper simulator")
    args = ap.parse_args()
    print(json.dumps(run(args.seconds, args.poll_seconds, not args.no_paper), indent=2, allow_nan=False))

if __name__ == "__main__": main()
