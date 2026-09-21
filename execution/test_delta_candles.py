import sys
import time
from pathlib import Path
from datetime import datetime, timezone

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from execution.delta_client import DeltaPublicClient
from data.market_state import (
    normalize_candle,
    aggregate_daily_to_monthly,
    candle_summary,
)


SYMBOL = "BTCUSD"
RESOLUTION = "1d"


def main():

    client = DeltaPublicClient()

    now = int(time.time())

    # Approximately 400 days of daily data.
    start = now - 400 * 24 * 60 * 60

    print("=" * 70)
    print("DELTA BTC DAILY -> MONTHLY AGGREGATION TEST")
    print("=" * 70)

    response = client.get_candles(
        symbol=SYMBOL,
        resolution=RESOLUTION,
        start=start,
        end=now,
    )

    if not isinstance(response, dict):
        raise RuntimeError(
            f"Unexpected response type: {type(response)}"
        )

    print("Response keys:", list(response.keys()))

    raw_candles = response.get("result", [])

    if not raw_candles:
        raise RuntimeError(
            "Delta returned no daily candles."
        )

    print("Raw daily candles:", len(raw_candles))

    daily = [
        normalize_candle(c)
        for c in raw_candles
    ]

    daily.sort(
        key=lambda c: c.timestamp
    )

    monthly = aggregate_daily_to_monthly(
        daily
    )

    print("Aggregated monthly candles:", len(monthly))

    print()
    print("First monthly candle:")
    print(candle_summary(monthly[0]))

    print()
    print("Last monthly candle:")
    print(candle_summary(monthly[-1]))

    print()
    print("Recent monthly candles:")

    for candle in monthly[-6:]:

        dt = datetime.fromtimestamp(
            candle.timestamp,
            tz=timezone.utc,
        )

        print(
            dt.strftime("%Y-%m"),
            f"O={candle.open:.2f}",
            f"H={candle.high:.2f}",
            f"L={candle.low:.2f}",
            f"C={candle.close:.2f}",
        )

    print()
    print("Daily -> monthly aggregation: PASS")


if __name__ == "__main__":
    main()
