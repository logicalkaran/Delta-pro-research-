import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paper.paper_engine import PaperEngine
from storage.trades import TradeStore


def main():
    with tempfile.TemporaryDirectory() as d:
        e = PaperEngine("BTCUSD", TradeStore(Path(d) / "trades.json"))
        e.submit("sell", 0.001, 100000, 5000, 1)
        assert e.position.side == "short"
        assert e.unrealized_pnl(99000) == 1.0
        e.submit("buy", 0.001, 99000, 4950, 2)
        assert not e.has_position()
    print("Short open/close and PnL: PASS")

if __name__ == "__main__":
    main()
