import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from paper.paper_engine import PaperEngine
from storage.trades import TradeStore


def main():

    print("=" * 70)
    print("PAPER ENGINE TEST")
    print("=" * 70)

    with tempfile.TemporaryDirectory() as temp_dir:

        trade_store = TradeStore(
            Path(temp_dir) / "paper_trades.json"
        )

        engine = PaperEngine(
            symbol="BTCUSD",
            trade_store=trade_store,
        )

        order = engine.submit(
            side="buy",
            quantity=0.001,
            price=85000,
            notional_inr=5000,
            timestamp=1789948800,
        )

        print()
        print("Order ID :", order.order_id)
        print("Symbol   :", order.symbol)
        print("Side     :", order.side)
        print("Quantity :", order.quantity)
        print("Price    :", order.price)

        assert order.order_id == "PAPER-000001"
        assert engine.has_position()

        position_value = engine.position_notional(
            86000
        )

        print(
            "Position mark value:",
            position_value,
        )

        assert position_value == 86.0

        close_order = engine.submit(
            side="sell",
            quantity=0.001,
            price=86000,
            notional_inr=5000,
            timestamp=1790000000,
        )

        print()
        print("Close order:", close_order.order_id)

        assert close_order.order_id == "PAPER-000002"
        assert not engine.has_position()

        # The temporary store disappears when the
        # test exits. Production state is untouched.

    print()
    print("Test isolation: PASS")
    print("Paper order lifecycle: PASS")


if __name__ == "__main__":
    main()
