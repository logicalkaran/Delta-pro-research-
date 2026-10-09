import csv
import sys
import time
from pathlib import Path
from datetime import datetime, timezone

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from execution.delta_client import DeltaPublicClient
from data.market_state import normalize_candle
from data.monthly_feed import MonthlyMarketFeed


RESEARCH_FILE = Path.home() / "data" / "BTC-USD_monthly.csv"
SYMBOL = "BTCUSD"


def load_research():

    with RESEARCH_FILE.open() as f:
        rows = list(csv.DictReader(f))

    result = {}

    for row in rows:

        month = row["Date"][:7]

        if month == "2026-09":
            continue

        result[month] = {
            "open": float(row["Open"]),
            "high": float(row["High"]),
            "low": float(row["Low"]),
            "close": float(row["Close"]),
        }

    return result


def pct(delta, reference):

    return abs(delta) / reference * 100.0


def main():

    print("=" * 70)
    print("RESEARCH vs DELTA OHLC DRIFT AUDIT")
    print("=" * 70)

    research = load_research()

    client = DeltaPublicClient()

    now = int(time.time())

    start = now - 800 * 24 * 60 * 60

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

    delta_monthly = MonthlyMarketFeed(
        daily
    ).completed_months()

    delta = {}

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

    print()
    print("Overlap:", len(overlap))

    print()
    print(
        f"{'MONTH':<10}"
        f"{'OPEN%':>10}"
        f"{'HIGH%':>10}"
        f"{'LOW%':>10}"
        f"{'CLOSE%':>10}"
    )

    print("-" * 50)

    max_drift = {
        "open": 0.0,
        "high": 0.0,
        "low": 0.0,
        "close": 0.0,
    }

    for month in overlap:

        r = research[month]
        d = delta[month]

        drifts = {
            "open": pct(d["open"] - r["open"], r["open"]),
            "high": pct(d["high"] - r["high"], r["high"]),
            "low": pct(d["low"] - r["low"], r["low"]),
            "close": pct(d["close"] - r["close"], r["close"]),
        }

        for key in max_drift:
            max_drift[key] = max(
                max_drift[key],
                drifts[key],
            )

        print(
            f"{month:<10}"
            f"{drifts['open']:>9.3f}%"
            f"{drifts['high']:>9.3f}%"
            f"{drifts['low']:>9.3f}%"
            f"{drifts['close']:>9.3f}%"
        )

    print()
    print("Maximum absolute drift:")
    print(f"  Open : {max_drift['open']:.3f}%")
    print(f"  High : {max_drift['high']:.3f}%")
    print(f"  Low  : {max_drift['low']:.3f}%")
    print(f"  Close: {max_drift['close']:.3f}%")

    print()
    print("OHLC SOURCE AUDIT: COMPLETE")


if __name__ == "__main__":
    main()
