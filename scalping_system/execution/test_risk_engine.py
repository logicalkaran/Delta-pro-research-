import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from risk.limits import RiskEngine


BTC_USD = 78557.50
USD_INR = 90.0


def check(name, decision, expected):
    assert decision.allowed is expected, (
        f"{name}: expected {expected}, "
        f"got {decision.allowed} "
        f"({decision.reason})"
    )

    print(
        f"{name}: PASS "
        f"({decision.reason})"
    )


def main():

    print("=" * 70)
    print("RISK ENGINE TEST")
    print("=" * 70)

    risk = RiskEngine(
        live_trading=False,
        max_positions=1,
        max_position_notional_inr=10000,
        max_daily_loss_inr=250,
        max_order_notional_inr=10000,
        kill_switch=True,
        contract_value_btc=0.001,
    )

    # One BTCUSD contract is approximately ₹7,070
    # at the test price and FX rate, so ₹10,000 permits
    # exactly one minimum contract.
    check(
        "Normal order",
        risk.check(
            order_notional_inr=10000,
            current_positions=0,
            daily_loss_inr=0,
            btc_usd_price=BTC_USD,
            usd_inr=USD_INR,
        ),
        True,
    )

    # Order exceeds hard order limit.
    check(
        "Order limit",
        risk.check(
            order_notional_inr=10001,
            current_positions=0,
            daily_loss_inr=0,
            btc_usd_price=BTC_USD,
            usd_inr=USD_INR,
        ),
        False,
    )

    # Existing position blocks another position.
    check(
        "Position limit",
        risk.check(
            order_notional_inr=10000,
            current_positions=1,
            daily_loss_inr=0,
            btc_usd_price=BTC_USD,
            usd_inr=USD_INR,
        ),
        False,
    )

    # Daily loss limit.
    check(
        "Daily loss limit",
        risk.check(
            order_notional_inr=10000,
            current_positions=0,
            daily_loss_inr=250,
            btc_usd_price=BTC_USD,
            usd_inr=USD_INR,
        ),
        False,
    )

    # Kill switch.
    check(
        "Kill switch",
        risk.check(
            order_notional_inr=10000,
            current_positions=0,
            daily_loss_inr=0,
            btc_usd_price=BTC_USD,
            usd_inr=USD_INR,
            kill_switch_active=True,
        ),
        False,
    )

    # Invalid notional.
    check(
        "Invalid notional",
        risk.check(
            order_notional_inr=0,
            current_positions=0,
            daily_loss_inr=0,
            btc_usd_price=BTC_USD,
            usd_inr=USD_INR,
        ),
        False,
    )

    # Minimum-contract protection.
    check(
        "Minimum contract protection",
        risk.check(
            order_notional_inr=5000,
            current_positions=0,
            daily_loss_inr=0,
            btc_usd_price=BTC_USD,
            usd_inr=USD_INR,
        ),
        False,
    )

    print()
    print("Risk engine: PASS")


if __name__ == "__main__":
    main()
