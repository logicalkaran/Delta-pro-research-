import csv
from pathlib import Path

from strategy.fisher import Candle, MonthlyFisher


DATA_FILE = Path.home() / "data" / "BTC-USD_monthly.csv"

EXPECTED = {
    "2015-10": (-0.727705, -1.224914),
    "2016-11": (2.429659, 2.244583),
    "2017-09": (3.902167, 3.835876),
    "2019-03": (-3.166391, -3.229259),
    "2020-05": (-0.288324, -0.310508),
    "2021-10": (1.173732, 1.042137),
    "2023-01": (-3.364455, -3.740139),
    "2023-10": (1.559736, 1.348908),
    "2024-11": (2.141810, 1.930608),
    "2025-05": (1.645580, 1.601350),
    "2026-08": (-2.040917, -2.250828),
}


def load():

    rows = []

    with DATA_FILE.open() as f:
        reader = csv.DictReader(f)

        for row in reader:

            rows.append(
                Candle(
                    timestamp=len(rows),
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                )
            )

    return rows


def main():

    candles = load()

    fisher = MonthlyFisher()

    results = []

    for candle in candles:

        result = fisher.update(candle)

        if result is None:
            continue

        # Recover the corresponding month from the CSV index.
        # Re-read the date separately below.
        results.append(result)

    # Run again with dates so the verification is explicit.
    with DATA_FILE.open() as f:
        reader = csv.DictReader(f)

        fisher = MonthlyFisher()

        found = {}

        for row in reader:

            candle = Candle(
                timestamp=0,
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
            )

            result = fisher.update(candle)

            if result is None:
                continue

            month = row["Date"][:7]

            if result.bullish_cross:
                found[month] = (
                    result.fisher,
                    result.trigger,
                )

    print("=" * 70)
    print("PRODUCTION FISHER REPRODUCTION TEST")
    print("=" * 70)
    print()

    failures = []

    for month, (expected_f, expected_t) in EXPECTED.items():

        if month not in found:
            print(f"FAIL {month}: signal not found")
            failures.append(month)
            continue

        actual_f, actual_t = found[month]

        fisher_ok = abs(actual_f - expected_f) < 1e-5
        trigger_ok = abs(actual_t - expected_t) < 1e-5

        ok = fisher_ok and trigger_ok

        print(
            f"{'PASS' if ok else 'FAIL'} {month} "
            f"Fisher={actual_f:.6f} "
            f"Trigger={actual_t:.6f}"
        )

        if not ok:
            failures.append(month)

    print()
    print("Detected bullish crossovers:")
    for month in found:
        print(
            f"  {month}: "
            f"Fisher={found[month][0]:.6f} "
            f"Trigger={found[month][1]:.6f}"
        )

    print()

    if failures:
        print("RESULT: FAILED")
        print("Mismatches:", ", ".join(failures))
        raise SystemExit(1)

    if list(found.keys()) != list(EXPECTED.keys()):
        print(
            "WARNING: crossover set differs from frozen "
            "research expectation."
        )
        raise SystemExit(1)

    print("RESULT: PASS")
    print("Production Fisher matches frozen research specification.")


if __name__ == "__main__":
    main()
