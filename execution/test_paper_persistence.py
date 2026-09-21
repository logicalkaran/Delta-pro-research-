import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from paper.paper_engine import PaperEngine
from storage.trades import TradeStore


def main():

    print("=" * 70)
    print("PAPER ENGINE PERSISTENCE TEST")
    print("=" * 70)

    with tempfile.TemporaryDirectory() as temp_dir:

        path = (
            Path(temp_dir)
            / "paper_trades.json"
        )

        store1 = TradeStore(path)

        engine1 = PaperEngine(
            symbol="BTCUSD",
            trade_store=store1,
        )

        order = engine1.submit(
            side="buy",
            quantity=0.001,
            price=78557.5,
            notional_inr=7070.175,
            timestamp=1000,
        )

        assert order.order_id == "PAPER-000001"
        assert engine1.has_position()
        assert len(engine1.orders) == 1

        print()
        print("Initial paper order: PASS")
        print("Order ID:", order.order_id)

        # Simulate process restart.
        store2 = TradeStore(path)

        engine2 = PaperEngine(
            symbol="BTCUSD",
            trade_store=store2,
        )

        assert engine2.has_position()
        assert len(engine2.orders) == 1
        assert engine2.position.quantity == 0.001
        assert engine2.position.entry_price == 78557.5

        print(
            "Position restored after restart: PASS"
        )
        print(
            "Orders restored after restart: PASS"
        )

        # Verify the counter also survives restart.
        sell = engine2.submit(
            side="sell",
            quantity=0.001,
            price=80000.0,
            notional_inr=7200.0,
            timestamp=2000,
        )

        assert sell.order_id == "PAPER-000002"
        assert not engine2.has_position()
        assert len(engine2.orders) == 2

        print(
            "Order counter survives restart: PASS"
        )
        print(
            "Position close persistence: PASS"
        )

        # Third process must see the closed position.
        store3 = TradeStore(path)

        engine3 = PaperEngine(
            symbol="BTCUSD",
            trade_store=store3,
        )

        assert not engine3.has_position()
        assert len(engine3.orders) == 2

        print(
            "Closed position restored after restart: PASS"
        )

    print()
    print("Paper engine persistence: PASS")


if __name__ == "__main__":
    main()
