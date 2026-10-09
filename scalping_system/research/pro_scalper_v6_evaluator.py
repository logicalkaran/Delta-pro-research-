"""Offline evaluator for V6 paper trades. Research-only; never submits orders."""
from __future__ import annotations
import json, math, statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "data/processed/pro_scalper_v6_paper.jsonl"
OUT = ROOT / "data/processed/pro_scalper_v6_evaluation.json"

def load_trades():
    if not LOG.exists():
        return []
    out = []
    for line in LOG.read_text().splitlines():
        try:
            r = json.loads(line)
            t = r.get("trade")
            if isinstance(t, dict) and t.get("exit_reason") in {"TARGET","STOP","TIMEOUT"}:
                out.append(t)
        except Exception:
            pass
    return out

def pf(xs):
    wins = sum(x for x in xs if x > 0)
    losses = -sum(x for x in xs if x < 0)
    return wins / losses if losses > 0 else (float("inf") if wins > 0 else 0.0)

def summarize(ts):
    net = [float(t["net_bps"]) for t in ts]
    pnl = [float(t["pnl_usd"]) for t in ts]
    mid = len(ts) // 2
    if mid:
        first, second = net[:mid], net[mid:]
    else:
        first, second = net, []
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for x in pnl:
        equity += x
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
    return {
        "completed_trades": len(ts),
        "wins": sum(x > 0 for x in net),
        "losses": sum(x <= 0 for x in net),
        "win_rate": (sum(x > 0 for x in net) / len(net)) if net else 0.0,
        "avg_net_bps": statistics.fmean(net) if net else 0.0,
        "median_net_bps": statistics.median(net) if net else 0.0,
        "profit_factor": pf(net),
        "total_net_bps": sum(net),
        "total_pnl_usd": sum(pnl),
        "max_drawdown_usd": max_dd,
        "positive_both_halves": bool(first and second and statistics.fmean(first) > 0 and statistics.fmean(second) > 0),
        "first_half_avg_net_bps": statistics.fmean(first) if first else 0.0,
        "second_half_avg_net_bps": statistics.fmean(second) if second else 0.0,
        "target_exits": sum(t["exit_reason"] == "TARGET" for t in ts),
        "stop_exits": sum(t["exit_reason"] == "STOP" for t in ts),
        "timeout_exits": sum(t["exit_reason"] == "TIMEOUT" for t in ts),
    }

def main():
    trades = load_trades()
    s = summarize(trades)
    req = {
        "completed_trades": 100,
        "profit_factor": 1.2,
        "win_rate": 0.52,
        "avg_net_bps": 0.5,
        "positive_both_halves": True,
    }
    ready = (
        s["completed_trades"] >= req["completed_trades"]
        and s["profit_factor"] >= req["profit_factor"]
        and s["win_rate"] >= req["win_rate"]
        and s["avg_net_bps"] >= req["avg_net_bps"]
        and s["positive_both_halves"]
    )
    result = {
        "schema": "pro_scalper_v6_evaluation",
        "research_only": True,
        "real_orders": False,
        "summary": s,
        "promotion_requirements": req,
        "promotion_ready": ready,
    }
    OUT.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
