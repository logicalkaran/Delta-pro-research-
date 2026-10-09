import json
import statistics
from pathlib import Path


INPUT = Path(
    "data/processed/research_sessions/"
    "btc_research_20260922_095821_canonical_features.jsonl"
)

HORIZONS = [1, 5, 10, 30]

BUCKETS = [
    ("strong_negative", float("-inf"), -0.60),
    ("negative", -0.60, -0.20),
    ("neutral", -0.20, 0.20),
    ("positive", 0.20, 0.60),
    ("strong_positive", 0.60, float("inf")),
]


def load_rows():

    rows = []

    with INPUT.open() as f:

        for line in f:

            line = line.strip()

            if not line:
                continue

            row = json.loads(line)

            if (
                row.get("l1_imbalance") is None
                or row.get("best_bid") is None
                or row.get("best_ask") is None
                or row.get("mid_price") is None
            ):
                continue

            rows.append(row)

    rows.sort(
        key=lambda x: x["trade_ts"]
    )

    return rows


def bucket(value):

    for name, low, high in BUCKETS:

        if low <= value < high:
            return name

    return None


def future_index(rows, index, seconds):

    target = (
        rows[index]["trade_ts"]
        + seconds * 1_000_000
    )

    for j in range(index + 1, len(rows)):

        if rows[j]["trade_ts"] >= target:
            return j

    return None


def main():

    rows = load_rows()

    print("=" * 78)
    print("L1 IMBALANCE COST-AWARE RESEARCH V1")
    print("=" * 78)

    print(f"INPUT ROWS : {len(rows)}")

    for age_name, age_limit in [
        ("all", None),
        ("100ms", 100_000),
        ("50ms", 50_000),
    ]:

        print()
        print("=" * 78)
        print(f"BOOK AGE FILTER: {age_name}")
        print("=" * 78)

        for horizon in HORIZONS:

            data = {
                name: {
                    "mid": [],
                    "long_exec": [],
                    "short_exec": [],
                }
                for name, _, _ in BUCKETS
            }

            for i, row in enumerate(rows):

                age = row.get("book_age_us")

                if age_limit is not None:

                    if age is None or age > age_limit:
                        continue

                j = future_index(
                    rows,
                    i,
                    horizon
                )

                if j is None:
                    continue

                name = bucket(
                    float(row["l1_imbalance"])
                )

                if name is None:
                    continue

                current_mid = float(
                    row["mid_price"]
                )

                current_ask = float(
                    row["best_ask"]
                )

                current_bid = float(
                    row["best_bid"]
                )

                future_mid = float(
                    rows[j]["mid_price"]
                )

                mid_return = (
                    future_mid / current_mid
                ) - 1.0

                # Immediate executable entry:
                # long enters at ask.
                # short enters at bid.
                #
                # Exit is evaluated against future mid.
                #
                # This is deliberately conservative and
                # does NOT model actual queue execution.

                long_return = (
                    future_mid / current_ask
                ) - 1.0

                short_return = (
                    current_bid / future_mid
                ) - 1.0

                data[name]["mid"].append(
                    mid_return
                )

                data[name]["long_exec"].append(
                    long_return
                )

                data[name]["short_exec"].append(
                    short_return
                )

            print()
            print(f"HORIZON {horizon}s")

            for name, _, _ in BUCKETS:

                values = data[name]

                n = len(values["mid"])

                if n == 0:
                    continue

                print()
                print(name)

                print(
                    f"  N              : {n}"
                )

                print(
                    f"  mid mean       : "
                    f"{statistics.mean(values['mid']):+.8f}"
                )

                print(
                    f"  long executable: "
                    f"{statistics.mean(values['long_exec']):+.8f}"
                )

                print(
                    f"  short executable: "
                    f"{statistics.mean(values['short_exec']):+.8f}"
                )


if __name__ == "__main__":
    main()
