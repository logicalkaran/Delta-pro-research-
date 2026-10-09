"""Real-risk-equivalent paper evaluator for Delta Exchange India BTCUSD.
No live orders. Uses current Delta contract constraints.
"""
from pathlib import Path
import json,time
ROOT=Path(__file__).resolve().parents[1]
STATE=ROOT/"data/live_microstructure_state.json"
OUT=ROOT/"data/processed/real_risk_equivalent_v1.json"
EQUITY=2.0
MIN_BTC=0.001
MAX_LEV=200.0
TAKER_BPS=5.0
SLIP_BPS=4.0
ADV_BPS=3.0
MAX_DD=.20

def main():
    try:
        s=json.loads(STATE.read_text())
        px=float(s.get("order_book",{}).get("mid_price",0))
    except Exception:
        px=0
    notional=MIN_BTC*px
    margin=notional/MAX_LEV if px else 0
    risk_if_1pct_move=notional*.01
    round_cost=notional*2*(TAKER_BPS+SLIP_BPS+ADV_BPS)/10000
    result={
      "updated_at":int(time.time()),
      "venue":"Delta Exchange India",
      "contract":"BTCUSD",
      "equity":EQUITY,
      "btc_price":px,
      "minimum_quantity_btc":MIN_BTC,
      "max_leverage":MAX_LEV,
      "notional_usd":notional,
      "required_margin_at_max_leverage_usd":margin,
      "margin_multiple_of_equity":margin/EQUITY if EQUITY else None,
      "loss_per_1pct_move_usd":risk_if_1pct_move,
      "round_trip_cost_conservative_usd":round_cost,
      "max_drawdown_usd":EQUITY*MAX_DD,
      "venue_feasible_at_max_leverage":margin<=EQUITY,
      "live_orders":False,
      "paper_only":True,
      "interpretation":"FEASIBLE_CONTRACT_SIZE_BUT_EXTREMELY_HIGH_RISK"
        if margin<=EQUITY else "INFEASIBLE_AT_CURRENT_BALANCE"
    }
    OUT.write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))

if __name__=="__main__":
    main()
