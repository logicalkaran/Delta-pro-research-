import sys
import time
from pathlib import Path
from datetime import datetime, timezone

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from execution.delta_client import DeltaPublicClient
from data.market_state import normalize_candle
from data.monthly_feed import MonthlyMarketFeed


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

    all_months = feed.monthly_candles()
    completed = feed.completed_months()
    incomplete = feed.incomplete_month()

    print("=" * 70)
    print("MONTHLY CLOSED-CANDLE SAFETY TEST")
    print("=" * 70)

    print("All monthly candles       :", len(all_months))
    print("Completed monthly candles :", len(completed))

    print()

    if incomplete is None:
        print("Incomplete current month  : NONE")
    else:
        dt = datetime.fromtimestamp(
            incomplete.timestamp,
            tz=timezone.utc,
        )

        print(
            "Incomplete current month :",
            dt.strftime("%Y-%m"),
        )

    print()

    if not completed:
        raise RuntimeError(
            "No completed monthly candles."
        )

    last_completed = completed[-1]

    dt = datetime.fromtimestamp(
        last_completed.timestamp,
        tz=timezone.utc,
    )

    print(
        "Last completed month      :",
        dt.strftime("%Y-%m"),
    )

    if incomplete is not None:

        incomplete_month = datetime.fromtimestamp(
            incomplete.timestamp,
            tz=timezone.utc,
        ).strftime("%Y-%m")

        completed_month = dt.strftime("%Y-%m")

        if incomplete_month == completed_month:
            raise RuntimeError(
                "SAFETY FAILURE: incomplete month "
                "was included as completed."
            )

    print()
    print("Closed-candle protection: PASS")


if __name__ == "__main__":
    main()
