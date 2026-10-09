"""Venue feasibility guard for the $2 paper challenge."""
import json,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data/processed/micro_challenge_feasibility_v1.json"
def main():
    px=0.0
    p=ROOT/"data/live_microstructure_state.json"
    try:px=float(json.loads(p.read_text()).get("order_book",{}).get("mid_price",0))
    except Exception:pass
    min_btc=0.001; leverage=3.0; equity=2.0
    margin=min_btc*px/leverage if px else 0
    result={"updated_at":int(time.time()),"btc_price":px,"minimum_btc":min_btc,
            "assumed_leverage":leverage,"minimum_margin_usd":margin,
            "equity_usd":equity,"venue_feasible":bool(px and margin<=equity),
            "paper_challenge_allowed":True,"real_orders":False}
    OUT.write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
if __name__=="__main__":main()
