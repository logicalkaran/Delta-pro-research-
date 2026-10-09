import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from execution.delta_client import DeltaPublicClient


def main():

    client = DeltaPublicClient()

    now = int(time.time())

    # Ask for approximately 5 years.
    start = now - 5 * 365 * 24 * 60 * 60

    print("=" * 70)
    print("DELTA HISTORICAL CANDLE LIMIT PROBE")
    print("=" * 70)

    response = client.get_candles(
        symbol="BTCUSD",
        resolution="1d",
        start=start,
        end=now,
    )

    candles = response.get("result", [])

    print("Requested days :", 5 * 365)
    print("Returned       :", len(candles))

    if candles:
        timestamps = [
            int(float(c[0] if isinstance(c, (list, tuple)) else
                    c.get("timestamp", c.get("time", c.get("start")))))
            for c in candles
        ]

        print("First timestamp:", min(timestamps))
        print("Last timestamp :", max(timestamps))

    print()
    print("PROBE COMPLETE")


if __name__ == "__main__":
    main()
