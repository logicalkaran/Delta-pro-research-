import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from execution.delta_client import DeltaPublicClient
from data.market_state import normalize_candle
from data.monthly_feed import MonthlyMarketFeed
from strategy.signal import FisherSignalEngine


SYMBOL = "BTCUSD"


def main():

    client = DeltaPublicClient()

    now = int(time.time())
    start = now - 400 * 24 * 60 * 60

    response = client.get_candles(
        symbol=SYMBOL,
        resolution="1d",
        start=start,
        end=now,
    )

    raw = response.get("result", [])

    daily = [
        normalize_candle(candle)
        for candle in raw
    ]

    feed = MonthlyMarketFeed(daily)
    completed = feed.completed_months()

    engine = FisherSignalEngine()

    signals = []

    for candle in completed:

        signal = engine.process(candle)

        if signal is not None:
            signals.append(signal)

    print("=" * 70)
    print("FISHER SIGNAL PIPELINE TEST")
    print("=" * 70)

    print("Completed candles:", len(completed))
    print("Fisher outputs    :", len(signals))

    print()
    print("Recent Fisher state:")

    for signal in signals[-5:]:
        print(
            f"{signal.month} "
            f"F={signal.fisher:.6f} "
            f"T={signal.trigger:.6f} "
            f"Cross={signal.bullish_cross}"
        )

    crosses = [
        signal
        for signal in signals
        if signal.bullish_cross
    ]

    print()
    print("Bullish crossovers:")

    for signal in crosses:
        print(
            f"  {signal.month}: "
            f"F={signal.fisher:.6f} "
            f"T={signal.trigger:.6f}"
        )

    print()
    print("Pipeline: PASS")


if __name__ == "__main__":
    main()
