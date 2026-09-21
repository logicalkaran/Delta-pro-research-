import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from risk.limits import RiskEngine


def main():

    print("=" * 70)
    print("RISK + POSITION SIZING INTEGRATION TEST")
    print("=" * 70)

    risk = RiskEngine(
        live_trading=False,
        max_positions=1,
        max_position_notional_inr=5000,
        max_daily_loss_inr=250,
        max_order_notional_inr=5000,
        kill_switch=True,
        contract_value_btc=0.001,
    )

    # ₹5,000 cannot purchase one BTCUSD contract
    # at this price/FX combination.
    rejected = risk.check(
        order_notional_inr=5000,
        current_positions=0,
        daily_loss_inr=0,
        btc_usd_price=78557.50,
        usd_inr=90.0,
    )

    print()
    print("₹5,000 test:")
    print("  allowed:", rejected.allowed)
    print("  reason :", rejected.reason)

    assert rejected.allowed is False
    assert (
        rejected.reason
        == "minimum_contract_exceeds_inr_limit"
    )

    # A larger ceiling should allow one contract.
    risk_larger = RiskEngine(
        live_trading=False,
        max_positions=1,
        max_position_notional_inr=10000,
        max_daily_loss_inr=250,
        max_order_notional_inr=10000,
        kill_switch=True,
        contract_value_btc=0.001,
    )

    allowed = risk_larger.check(
        order_notional_inr=10000,
        current_positions=0,
        daily_loss_inr=0,
        btc_usd_price=78557.50,
        usd_inr=90.0,
    )

    print()
    print("₹10,000 test:")
    print("  allowed:", allowed.allowed)
    print("  reason :", allowed.reason)

    assert allowed.allowed is True
    assert allowed.position_size is not None
    assert allowed.position_size.contracts == 1
    assert allowed.position_size.inr_notional <= 10000

    print()
    print("Risk + sizing integration: PASS")


if __name__ == "__main__":
    main()
