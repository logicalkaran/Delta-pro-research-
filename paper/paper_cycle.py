import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from execution.delta_history import DeltaDailyHistory
from data.market_state import aggregate_daily_to_monthly
from strategy.signal import FisherSignalEngine
from strategy.signal_validator import SignalValidator
from risk.limits import RiskEngine
from paper.paper_engine import PaperEngine


SYMBOL = "BTCUSD"


def get_usd_inr():
    value = os.getenv("USD_INR")

    if not value:
        raise RuntimeError(
            "USD_INR environment variable is required."
        )

    try:
        rate = float(value)
    except ValueError:
        raise RuntimeError(
            "USD_INR must be numeric."
        )

    if rate <= 0:
        raise RuntimeError(
            "USD_INR must be greater than zero."
        )

    return rate


def main():

    print("=" * 70)
    print("BTC MONTHLY FISHER — PAPER CYCLE")
    print("=" * 70)

    # ------------------------------------------------------------
    # 1. MARKET DATA
    # ------------------------------------------------------------

    now = int(time.time())

    history = DeltaDailyHistory()

    daily = history.fetch(
        start=now - 3 * 365 * 24 * 60 * 60,
        end=now,
    )

    print()
    print("Daily candles:", len(daily))

    # ------------------------------------------------------------
    # 2. MONTHLY AGGREGATION
    # ------------------------------------------------------------

    monthly = aggregate_daily_to_monthly(daily)

    # Never feed the incomplete current month.
    completed = monthly[:-1]

    print("Monthly candles:", len(monthly))
    print("Completed months:", len(completed))

    if not completed:
        raise RuntimeError(
            "No completed monthly candles."
        )

    # ------------------------------------------------------------
    # 3. FISHER
    # ------------------------------------------------------------

    signal_engine = FisherSignalEngine()

    signals = []

    for candle in completed:

        signal = signal_engine.process(candle)

        if signal is not None:
            signals.append(signal)

    if not signals:
        raise RuntimeError(
            "No Fisher outputs."
        )

    latest = signals[-1]

    print()
    print(
        "Latest Fisher:",
        f"{latest.month}",
        f"F={latest.fisher:.6f}",
        f"T={latest.trigger:.6f}",
        f"Cross={latest.bullish_cross}",
    )

    # ------------------------------------------------------------
    # 4. SIGNAL VALIDATION
    # ------------------------------------------------------------

    validator = SignalValidator()

    # Explicitly distinguish:
    #   - no bullish crossover
    #   - already processed crossover
    #   - new executable crossover

    if not latest.bullish_cross:

        print()
        print("Signal status : NO_BULLISH_CROSS")
        print("Signal ID     : NOT_CREATED")
        print("Risk status   : NOT_EVALUATED")
        print("Paper order   : NOT_SUBMITTED")
        print("REAL EXCHANGE ORDER: NO")
        print("LIVE TRADING: OFF")
        print("PAPER CYCLE: PASS")
        return

    signal_id = validator.make_signal_id(
        latest.month
    )

    if validator.is_processed(signal_id):

        print()
        print("Signal status : ALREADY_PROCESSED")
        print("Signal ID     :", signal_id)
        print("Risk status   : NOT_EVALUATED")
        print("Paper order   : NOT_SUBMITTED")
        print("REAL EXCHANGE ORDER: NO")
        print("LIVE TRADING: OFF")
        print("PAPER CYCLE: PASS")
        return

    validated = validator.validate(
        signal_month=latest.month,
        fisher=latest.fisher,
        trigger=latest.trigger,
        bullish_cross=latest.bullish_cross,
    )

    if validated is None:
        raise RuntimeError(
            "Signal validation returned None after "
            "crossover and duplicate checks passed."
        )

    print()
    print("Validated signal:")
    print("  ID:", validated.signal_id)
    print("  Signal month:", validated.signal_month)
    print("  Execution month:", validated.execution_month)

    # ------------------------------------------------------------
    # 5. MARKET / FX INPUTS
    # ------------------------------------------------------------

    execution_price = completed[-1].close
    usd_inr = get_usd_inr()

    target_notional_inr = 5000.0

    print()
    print("Execution price USD:", execution_price)
    print("USD/INR:", usd_inr)
    print("Target INR:", target_notional_inr)

    # ------------------------------------------------------------
    # 6. RISK + EXCHANGE CONTRACT SIZING
    # ------------------------------------------------------------

    risk = RiskEngine(
        live_trading=False,
        max_positions=1,
        max_position_notional_inr=5000,
        max_daily_loss_inr=250,
        max_order_notional_inr=5000,
        kill_switch=True,
        contract_value_btc=0.001,
    )

    decision = risk.check(
        order_notional_inr=target_notional_inr,
        current_positions=0,
        daily_loss_inr=0,
        btc_usd_price=execution_price,
        usd_inr=usd_inr,
        kill_switch_active=False,
    )

    print()
    print("Risk decision:")
    print("  Allowed:", decision.allowed)
    print("  Reason :", decision.reason)

    if decision.position_size is not None:
        size = decision.position_size

        print("  Contracts:", size.contracts)
        print("  BTC      :", size.quantity_btc)
        print("  USD      :", size.usd_notional)
        print("  INR      :", size.inr_notional)

    # ------------------------------------------------------------
    # 7. SAFE REJECTION
    # ------------------------------------------------------------

    if not decision.allowed:

        print()
        print("PAPER ORDER: NOT SUBMITTED")
        print("Reason:", decision.reason)
        print("REAL EXCHANGE ORDER: NO")
        print("LIVE TRADING: OFF")
        print("PAPER CYCLE: PASS")

        return

    # ------------------------------------------------------------
    # 8. PAPER EXECUTION
    # ------------------------------------------------------------

    size = decision.position_size

    if size is None:
        raise RuntimeError(
            "Risk allowed order without position sizing."
        )

    paper = PaperEngine(
        symbol=SYMBOL
    )

    order = paper.submit(
        side="buy",
        quantity=size.quantity_btc,
        price=execution_price,
        notional_inr=size.inr_notional,
    )

    print()
    print("Paper order:")
    print("  ID       :", order.order_id)
    print("  Symbol   :", order.symbol)
    print("  Side     :", order.side)
    print("  Quantity :", order.quantity)
    print("  Price    :", order.price)
    print("  INR      :", size.inr_notional)

    assert paper.has_position()

    # Commit the signal only after the paper order has
    # been successfully recorded.
    validator.mark_processed(validated)

    print()
    print("Signal state: COMMITTED")
    print("REAL EXCHANGE ORDER: NO")
    print("LIVE TRADING: OFF")
    print("PAPER CYCLE: PASS")


if __name__ == "__main__":
    main()
