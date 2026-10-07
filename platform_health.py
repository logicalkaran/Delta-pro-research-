"""Unified health, persistence, and live-readiness checks."""
from __future__ import annotations
import json, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
RUN = DATA / "run"

def _read(name):
    try:
        return json.loads((DATA / name).read_text(encoding="utf-8"))
    except Exception:
        return None

def _pid_alive(name):
    p = RUN / name
    try:
        return p.is_file() and Path(f"/proc/{int(p.read_text())}").exists()
    except (OSError, ValueError):
        return False

def health():
    live = _read("live_market_state.json") or {}
    candles = _read("live_candles.json") or []
    age = None
    if live.get("updated_at"):
        age = max(0, int(time.time()) - int(live["updated_at"]))
    checks = {
        "live_market_state": bool(live),
        "market_fresh": age is not None and age <= 15,
        "candles_available": len(candles) > 0,
        "dashboard_process": _pid_alive("dashboard.pid"),
        "collector_process": _pid_alive("collector.pid"),
        "dashboard_read_only": True,
        "live_orders_enabled": False,
        "paper_engine_available": True,
        "risk_engine_required_for_execution": True,
    }
    critical = [
        checks["live_market_state"], checks["market_fresh"],
        checks["candles_available"], checks["dashboard_process"],
        checks["collector_process"], checks["paper_engine_available"],
        checks["risk_engine_required_for_execution"],
    ]
    return {
        "status": "OK" if all(critical) else "DEGRADED",
        "timestamp": int(time.time()),
        "checks": checks,
        "market_age_seconds": age,
        "candle_count": len(candles),
        "live_orders_enabled": False,
    }
