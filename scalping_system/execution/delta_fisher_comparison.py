import csv
import sys
import time
from pathlib import Path
from datetime import datetime, timezone

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from execution.delta_history import DeltaDailyHistory
from data.market_state import (
    normalize_candle,
    aggregate_daily_to_monthly,
)
from strategy.fisher import MonthlyFisher


RESEARCH_FILE = Path.home() / "data" / "BTC-USD_monthly.csv"


def load_research():

    result = {}

    with RESEARCH_FILE.open() as f:
        rows = csv.DictReader(f)

        for row in rows:

            month = row["Date"][:7]

            if month == "2026-09":
                continue

            result[month] = {
                "fisher": None,
                "trigger": None,
            }

    engine = MonthlyFisher()

    with RESEARCH_FILE.open() as f:
        rows = csv.DictReader(f)

        for row in rows:

            month = row["Date"][:7]

            if month == "2026-09":
                continue

            from strategy.fisher import Candle

            candle = Candle(
                timestamp=int(
                    datetime.strptime(
                        row["Date"][:10],
                        "%Y-%m-%d",
                    ).replace(
                        tzinfo=timezone.utc
                    ).timestamp()
                ),
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
            )

            value = engine.update(candle)

            if value is not None:
                result[month] = {
                    "fisher": value.fisher,
                    "trigger": value.trigger,
                }

    return result


def month_key(timestamp):

    return datetime.fromtimestamp(
        timestamp,
        tz=timezone.utc,
    ).strftime("%Y-%m")


def main():

    print("=" * 70)
    print("DELTA FISHER vs FROZEN RESEARCH FISHER")
    print("=" * 70)

    now = int(time.time())

    collector = DeltaDailyHistory()

    daily = collector.fetch(
        start=now - 3 * 365 * 24 * 60 * 60,
        end=now,
    )

    monthly = aggregate_daily_to_monthly(
        daily
    )

    # Remove incomplete current month.
    monthly = [
        c for c in monthly
        if month_key(c.timestamp) != "2026-09"
    ]

    delta_engine = MonthlyFisher()

    delta_values = {}

    for candle in monthly:

        value = delta_engine.update(candle)

        if value is not None:
            delta_values[
                month_key(candle.timestamp)
            ] = {
                "fisher": value.fisher,
                "trigger": value.trigger,
            }

    research = load_research()

    overlap = sorted(
        set(delta_values) & set(research)
    )

    print()
    print("Delta monthly candles:", len(monthly))
    print("Overlap:", len(overlap))

    print()
    print(
        f"{'MONTH':<10}"
        f"{'R_FISHER':>12}"
        f"{'D_FISHER':>12}"
        f"{'F_DIFF':>12}"
    )

    print("-" * 50)

    for month in overlap:

        r = research[month]["fisher"]
        d = delta_values[month]["fisher"]

        if r is None or d is None:
            continue

        print(
            f"{month:<10}"
            f"{r:>12.6f}"
            f"{d:>12.6f}"
            f"{d-r:>12.6f}"
        )

    print()
    print(
        "Interpretation: this measures the effect of "
        "different data history + Fisher initialization."
    )


if __name__ == "__main__":
    main()
