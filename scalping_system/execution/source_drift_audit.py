import csv
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from execution.delta_client import DeltaPublicClient
from data.market_state import normalize_candle
from data.monthly_feed import MonthlyMarketFeed


RESEARCH_FILE = Path.home() / "data" / "BTC-USD_monthly.csv"
SYMBOL = "BTCUSD"


def load_research():

    rows = []

    with RESEARCH_FILE.open() as f:
        reader = csv.DictReader(f)

        for row in reader:

            date = row["Date"][:7]

            # Ignore incomplete current month.
            if date == "2026-09":
                continue

            rows.append({
                "month": date,
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
            })

    return {
        row["month"]: row
        for row in rows
    }


def main():

    print("=" * 70)
    print("RESEARCH vs DELTA SOURCE DRIFT AUDIT")
    print("=" * 70)

    research = load_research()

    client = DeltaPublicClient()

    now = int(time.time())

    # Pull enough daily history to cover the overlap.
    start = now - 800 * 24 * 60 * 60

    response = client.get_candles(
        symbol=SYMBOL,
        resolution="1d",
        start=start,
        end=now,
    )

    raw = response.get("result", [])

    if not raw:
        raise RuntimeError(
            "Delta returned no candles."
        )

    daily = [
        normalize_candle(candle)
        for candle in raw
    ]

    delta_monthly = MonthlyMarketFeed(
        daily
    ).completed_months()

    delta = {}

    from datetime import datetime, timezone

    for candle in delta_monthly:

        month = datetime.fromtimestamp(
            candle.timestamp,
            tz=timezone.utc,
        ).strftime("%Y-%m")

        delta[month] = {
            "open": candle.open,
            "high": candle.high,
            "low": candle.low,
            "close": candle.close,
        }

    overlap = sorted(
        set(research) & set(delta)
    )

    if not overlap:
        raise RuntimeError(
            "No overlapping months found."
        )

    print()
    print("Research months:", len(research))
    print("Delta months   :", len(delta))
    print("Overlap        :", len(overlap))

    print()
    print(
        f"{'MONTH':<10}"
        f"{'RESEARCH C':>14}"
        f"{'DELTA C':>14}"
        f"{'DIFF %':>12}"
    )

    print("-" * 52)

    for month in overlap:

        r_close = research[month]["close"]
        d_close = delta[month]["close"]

        diff_pct = (
            (d_close - r_close)
            / r_close
            * 100
        )

        print(
            f"{month:<10}"
            f"{r_close:>14.2f}"
            f"{d_close:>14.2f}"
            f"{diff_pct:>11.3f}%"
        )

    print()
    print("SOURCE DRIFT AUDIT: COMPLETE")


if __name__ == "__main__":
    main()
