import json
import statistics
from pathlib import Path


INPUT = Path(
    "data/processed/research_sessions/"
    "btc_research_20260922_095821_canonical_features.jsonl"
)

HORIZONS = [1, 5, 10, 30]

DURATIONS_US = [
    100_000,
    250_000,
    500_000,
    1_000_000,
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
                or row.get("mid_price") is None
            ):
                continue

            rows.append(row)

    rows.sort(key=lambda x: x["trade_ts"])

    return rows


def future_return(rows, index, seconds):
    target = (
        rows[index]["trade_ts"]
        + seconds * 1_000_000
    )

    current = float(rows[index]["mid_price"])

    for j in range(index + 1, len(rows)):
        if rows[j]["trade_ts"] >= target:
            future = float(rows[j]["mid_price"])

            if current <= 0:
                return None

            return (future / current) - 1.0

    return None


def qualifies(value, target):
    if target == "strong_positive":
        return value >= 0.60

    if target == "strong_negative":
        return value <= -0.60

    return False


def remains_persistent(
    rows,
    start_index,
    target,
    duration_us,
):
    start_ts = rows[start_index]["trade_ts"]
    end_ts = start_ts + duration_us

    for j in range(start_index + 1, len(rows)):

        ts = rows[j]["trade_ts"]

        if ts > end_ts:
            break

        age = rows[j].get("book_age_us")

        if age is None or age > 50_000:
            return False

        imbalance = float(
            rows[j]["l1_imbalance"]
        )

        if not qualifies(
            imbalance,
            target,
        ):
            return False

    return True


def main():

    rows = load_rows()

    print("=" * 78)
    print("IMBALANCE TIME-PERSISTENCE RESEARCH V1")
    print("=" * 78)

    print(f"INPUT ROWS : {len(rows)}")

    for target in [
        "strong_positive",
        "strong_negative",
    ]:

        print()
        print("=" * 78)
        print(target.upper())
        print("=" * 78)

        for duration in DURATIONS_US:

            qualifying = []

            for i, row in enumerate(rows):

                age = row.get("book_age_us")

                if (
                    age is None
                    or age > 50_000
                ):
                    continue

                imbalance = float(
                    row["l1_imbalance"]
                )

                if not qualifies(
                    imbalance,
                    target,
                ):
                    continue

                if remains_persistent(
                    rows,
                    i,
                    target,
                    duration,
                ):
                    qualifying.append(i)

            print()
            print(
                f"duration "
                f"{duration / 1000:.0f}ms"
            )

            print(
                f"events : {len(qualifying)}"
            )

            for horizon in HORIZONS:

                returns = []

                for index in qualifying:

                    ret = future_return(
                        rows,
                        index,
                        horizon,
                    )

                    if ret is not None:
                        returns.append(ret)

                if returns:
                    print(
                        f"  {horizon:2d}s "
                        f"N={len(returns):3d} "
                        f"mean="
                        f"{statistics.mean(returns):+.8f}"
                    )


if __name__ == "__main__":
    main()
