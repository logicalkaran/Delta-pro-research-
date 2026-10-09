"""BTC scalping strategy matrix v1 — research/paper analytics only.

Ranks existing forward-test strategy families by regime and horizon using the
already-resolved forward tournament outcomes. It never changes execution.
"""
from pathlib import Path
import json, time, math

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data/processed/strategy_forward_tournament_v1.jsonl"
OUT = ROOT / "data/processed/scalping_strategy_matrix_v1.json"
COST_BPS = 12.0
FAMILIES = (
    "MOMENTUM", "LIQUIDITY_SWEEP", "LEVEL_REACTION",
    "FLOW_CONTINUATION", "FLOW_MEAN_REVERSION", "ORDERBOOK_IMBALANCE",
)
REGIMES = ("LOW_VOL", "NORMAL_VOL", "HIGH_VOL")
HORIZONS = (1, 2, 3, 5)

def load_rows():
    rows = []
    if SRC.exists():
        for line in SRC.read_text().splitlines():
            try:
                x = json.loads(line)
                if x.get("strategy") in FAMILIES:
                    rows.append(x)
            except Exception:
                pass
    return rows

def stats(rows):
    vals = [float(x.get("net_return_pct", 0.0)) for x in rows]
    if not vals:
        return {"samples": 0, "win_rate": None, "avg_net_pct": None,
                "profit_factor": None, "positive": False}
    gains = sum(v for v in vals if v > 0)
    losses = abs(sum(v for v in vals if v < 0))
    pf = gains / losses if losses else (math.inf if gains else 0.0)
    return {
        "samples": len(vals),
        "win_rate": sum(v > 0 for v in vals) / len(vals),
        "avg_net_pct": sum(vals) / len(vals),
        "profit_factor": pf,
        "positive": sum(vals) > 0,
    }

def main():
    rows = load_rows()
    cells = []
    for family in FAMILIES:
        for regime in REGIMES:
            for horizon in HORIZONS:
                rs = [x for x in rows
                      if x.get("strategy") == family
                      and x.get("regime") == regime
                      and int(x.get("horizon", 0)) == horizon]
                s = stats(rs)
                # Research ranking only: require meaningful sample and positive expectancy.
                eligible = bool(
                    s["samples"] >= 30 and
                    s["avg_net_pct"] is not None and s["avg_net_pct"] > 0 and
                    (s["profit_factor"] or 0) >= 1.2
                )
                score = None
                if s["samples"]:
                    score = round(
                        100 * max(s["avg_net_pct"], -0.1)
                        * min(1.0, s["samples"] / 100.0)
                        * min(2.0, (s["profit_factor"] or 0) / 1.2),
                        4,
                    )
                cells.append({
                    "family": family, "regime": regime, "horizon_min": horizon,
                    **s, "eligible_for_paper_ranking": eligible, "research_score": score,
                    "cost_model_bps": COST_BPS,
                })

    ranked = sorted(
        [x for x in cells if x["eligible_for_paper_ranking"]],
        key=lambda x: (x["research_score"] or -999, x["avg_net_pct"] or -999),
        reverse=True,
    )
    out = {
        "updated_at": time.time(),
        "source": str(SRC),
        "cost_model_bps": COST_BPS,
        "families": list(FAMILIES),
        "regimes": list(REGIMES),
        "horizons_min": list(HORIZONS),
        "cells": cells,
        "top_paper_candidates": ranked[:12],
        "stable_candidates": [],
        "paper_only": True,
        "real_orders": False,
        "promotion_allowed": False,
        "promotion_note": "This matrix is a research selector. No live execution changes are permitted from its rankings.",
    }
    OUT.write_text(json.dumps(out, indent=2))
    print(json.dumps({
        "rows": len(rows),
        "cells": len(cells),
        "paper_candidates": len(ranked),
        "top": ranked[:5],
        "output": str(OUT),
    }, indent=2))

if __name__ == "__main__":
    main()
