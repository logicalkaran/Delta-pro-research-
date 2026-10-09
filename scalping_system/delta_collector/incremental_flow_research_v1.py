import json
import math
import statistics
from pathlib import Path


INPUT = Path(
    "data/processed/research_sessions/"
    "btc_research_20260922_095821_canonical_features.jsonl"
)

HORIZONS = [1, 5, 10, 30]


def pearson(x, y):
    if len(x) < 2 or len(x) != len(y):
        return None

    mx = statistics.mean(x)
    my = statistics.mean(y)

    numerator = sum(
        (a - mx) * (b - my)
        for a, b in zip(x, y)
    )

    dx = math.sqrt(
        sum((a - mx) ** 2 for a in x)
    )

    dy = math.sqrt(
        sum((b - my) ** 2 for b in y)
    )

    if dx == 0 or dy == 0:
        return None

    return numerator / (dx * dy)


def load_rows():
    rows = []

    with INPUT.open() as f:
        for line in f:
            line = line.strip()

            if not line:
                continue

            row = json.loads(line)

            if not row.get("mid_price_valid"):
                continue

            if not row.get("book_valid"):
                continue

            if not row.get("valid_side"):
                continue

            if row.get("l1_imbalance") is None:
                continue

            if row.get("trade_delta") is None:
                continue

            rows.append(row)

    rows.sort(
        key=lambda x: int(x["trade_ts"])
    )

    return rows


def future_return(rows, index, seconds):
    target = (
        int(rows[index]["trade_ts"])
        + seconds * 1_000_000
    )

    current = float(
        rows[index]["mid_price"]
    )

    for j in range(index + 1, len(rows)):
        if int(rows[j]["trade_ts"]) >= target:

            future = float(
                rows[j]["mid_price"]
            )

            if current <= 0:
                return None

            return (
                future / current
            ) - 1.0

    return None


def summarize(name, values, returns):
    pairs = [
        (x, y)
        for x, y in zip(values, returns)
        if x is not None and y is not None
    ]

    if len(pairs) < 2:
        print(
            f"{name:<24} N=0"
        )
        return

    x = [p[0] for p in pairs]
    y = [p[1] for p in pairs]

    print(
        f"{name:<24} "
        f"N={len(y):4d} "
        f"corr={pearson(x, y):+.6f} "
        f"mean_ret={statistics.mean(y):+.8f}"
    )


def main():

    rows = load_rows()

    print("=" * 82)
    print("INCREMENTAL FLOW RESEARCH V1")
    print("=" * 82)

    print(f"VALID ROWS : {len(rows)}")

    if not rows:
        print("No valid rows.")
        return

    for horizon in HORIZONS:

        l1_values = []
        delta_values = []
        combined_values = []
        returns = []

        fresh_l1 = []
        fresh_delta = []
        fresh_combined = []
        fresh_returns = []

        for i, row in enumerate(rows):

            ret = future_return(
                rows,
                i,
                horizon
            )

            if ret is None:
                continue

            l1 = float(
                row["l1_imbalance"]
            )

            delta = float(
                row["trade_delta"]
            )

            age = row.get("book_age_us")

            l1_values.append(l1)
            delta_values.append(delta)
            combined_values.append(
                l1 * (
                    1.0
                    if delta >= 0
                    else -1.0
                )
            )
            returns.append(ret)

            if age is not None and age <= 50_000:

                fresh_l1.append(l1)
                fresh_delta.append(delta)
                fresh_combined.append(
                    l1 * (
                        1.0
                        if delta >= 0
                        else -1.0
                    )
                )
                fresh_returns.append(ret)

        print()
        print("=" * 82)
        print(f"HORIZON {horizon}s")
        print("=" * 82)

        summarize(
            "L1",
            l1_values,
            returns
        )

        summarize(
            "Delta",
            delta_values,
            returns
        )

        summarize(
            "L1 x Delta direction",
            combined_values,
            returns
        )

        print()
        print("FRESH BOOK <= 50ms")

        summarize(
            "L1 fresh",
            fresh_l1,
            fresh_returns
        )

        summarize(
            "Delta fresh",
            fresh_delta,
            fresh_returns
        )

        summarize(
            "L1 x Delta fresh",
            fresh_combined,
            fresh_returns
        )


if __name__ == "__main__":
    main()
