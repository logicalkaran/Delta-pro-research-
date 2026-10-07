import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from execution.signal_to_delta import prepare_order

def main():
    r = prepare_order(
        decision="LONG", mark_price=86000, usd_inr=83,
        notional_inr=5000, client_order_id="TEST-SIGNAL-001"
    )
    assert r["allowed"] is False
    assert r["reason"] == "minimum_contract_exceeds_inr_limit"
    print("Signal -> Risk -> Delta safety block: PASS")
    print(r)

if __name__ == "__main__":
    main()
