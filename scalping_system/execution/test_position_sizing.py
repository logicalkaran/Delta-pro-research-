import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from risk.sizing import PositionSizer


def main():

    print("=" * 70)
    print("POSITION SIZING SAFETY TEST")
    print("=" * 70)

    sizer = PositionSizer(
        contract_value_btc=0.001,
        quantity_precision=3,
    )

    result = sizer.calculate(
        max_inr_notional=5000,
        btc_usd_price=78557.50,
        usd_inr=90.0,
    )

    one_contract_inr = (
        0.001
        * 78557.50
        * 90.0
    )

    print()
    print("BTC/USD:", 78557.50)
    print("USD/INR:", 90.0)
    print("Max INR:", 5000)
    print(
        "One-contract INR notional:",
        round(one_contract_inr, 2),
    )

    print()
    print("Allowed   :", result.allowed)
    print("Reason    :", result.reason)
    print("Contracts :", result.contracts)
    print("BTC       :", result.quantity_btc)
    print("INR       :", result.inr_notional)

    assert result.allowed is False
    assert result.contracts == 0
    assert result.quantity_btc == 0.0
    assert (
        result.reason
        == "minimum_contract_exceeds_inr_limit"
    )

    print()
    print(
        "Minimum-contract protection: PASS"
    )


if __name__ == "__main__":
    main()
