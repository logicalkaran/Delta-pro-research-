"""Minimum realistic capital calculator for the current BTC paper execution model.
No live orders. Uses the venue minimum quantity and conservative round-trip costs.
"""
from pathlib import Path
import json, time

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "data/live_microstructure_state.json"
OUT = ROOT / "data/processed/minimum_realistic_capital_v1.json"

MIN_BTC = 0.001
LEV = 3.0
FEE_BPS = 11.0
SLIP_BPS = 4.0
ADV_BPS = 3.0
TARGET_EQUITY = 4.0

# Capital tiers: maximum loss per trade as a fraction of equity.
RISK_TIERS = [0.01, 0.02, 0.05, 0.10]
STOP_SCENARIOS = [0.005, 0.01, 0.015, 0.02, 0.03]
LOSS_STREAKS = [1, 2, 3, 5]

def read_price():
    try:
        state = json.loads(STATE.read_text())
        return float(state.get("order_book", {}).get("mid_price", 0))
    except Exception:
        return 0.0

def main():
    px = read_price()
    notional = MIN_BTC * px
    margin = notional / LEV if px else 0.0
    round_trip_cost = notional * 2 * (FEE_BPS + SLIP_BPS + ADV_BPS) / 10000 if px else 0.0

    scenarios = []
    for stop_pct in STOP_SCENARIOS:
        gross_stop = notional * stop_pct
        for risk_frac in RISK_TIERS:
            capital_for_stop_risk = gross_stop / risk_frac if risk_frac else 0.0
            capital_for_cost = round_trip_cost / risk_frac if risk_frac else 0.0
            required = max(margin, capital_for_stop_risk, capital_for_cost)
            scenarios.append({
                "stop_pct": stop_pct,
                "risk_fraction": risk_frac,
                "gross_loss_at_stop_usd": round(gross_stop, 6),
                "round_trip_cost_usd": round(round_trip_cost, 6),
                "required_equity_usd": round(required, 4),
                "margin_feasible": required >= margin,
                "risk_budget_covers_cost": round_trip_cost <= required * risk_frac,
            })

    streaks = []
    for risk_frac in [0.01, 0.02, 0.05]:
        for losses in LOSS_STREAKS:
            # Conservative approximation: repeated full-risk losses, excluding compounding.
            required = margin
            streaks.append({
                "risk_fraction": risk_frac,
                "losses": losses,
                "capital_to_absorb_streak_usd": round(required, 4),
                "drawdown_fraction_approx": round(risk_frac * losses, 4),
                "within_10pct_dd": risk_frac * losses <= 0.10,
                "within_20pct_dd": risk_frac * losses <= 0.20,
            })

    one_pct_1pct_risk = next(
        x["required_equity_usd"] for x in scenarios
        if x["stop_pct"] == 0.01 and x["risk_fraction"] == 0.01
    )
    one_pct_2pct_risk = next(
        x["required_equity_usd"] for x in scenarios
        if x["stop_pct"] == 0.01 and x["risk_fraction"] == 0.02
    )

    result = {
        "updated_at": int(time.time()),
        "btc_price_usd": px,
        "minimum_quantity_btc": MIN_BTC,
        "minimum_notional_usd": round(notional, 4),
        "minimum_margin_usd_at_3x": round(margin, 4),
        "round_trip_cost_usd": round(round_trip_cost, 4),
        "target_equity_usd": TARGET_EQUITY,
        "key_reference": {
            "1pct_stop_1pct_risk_min_equity_usd": round(one_pct_1pct_risk, 4),
            "1pct_stop_2pct_risk_min_equity_usd": round(one_pct_2pct_risk, 4),
            "cost_only_1pct_risk_min_equity_usd": round(round_trip_cost / 0.01, 4),
        },
        "capital_tiers": [
            {"equity_usd": 2.0, "venue_margin_feasible": 2.0 >= margin},
            {"equity_usd": 25.0, "venue_margin_feasible": 25.0 >= margin},
            {"equity_usd": 50.0, "venue_margin_feasible": 50.0 >= margin},
            {"equity_usd": 100.0, "venue_margin_feasible": 100.0 >= margin},
            {"equity_usd": 250.0, "venue_margin_feasible": 250.0 >= margin},
        ],
        "stop_risk_matrix": scenarios,
        "loss_streak_matrix": streaks,
        "live_orders": False,
        "paper_only": True,
        "interpretation": (
            "DO_NOT_TRADE_REAL_MONEY_AT_CURRENT_BALANCE"
            if 2.0 < margin or 2.0 < one_pct_2pct_risk
            else "CAPITAL_MEETS_BASIC_CONSTRAINTS_BUT_VALIDATION_GATE_STILL_REQUIRED"
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
