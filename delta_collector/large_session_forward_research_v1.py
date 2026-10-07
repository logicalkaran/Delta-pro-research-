import json
import math
import statistics
from pathlib import Path


INPUT = Path(
    "data/processed/research_sessions/"
    "btc_research_20260922_095821_synchronized_features.jsonl"
)

HORIZONS = [1, 5, 10, 30]

AGE_LIMITS = [
    ("all", None),
    ("100ms", 100_000),
    ("50ms", 50_000),
    ("20ms", 20_000),
]


def load_rows():
    rows = []

    with INPUT.open() as f:
        for line in f:

            line = line.strip()

            if not line:
                continue

            row = json.loads(line)

            if row.get("trade_ts") is None:
                continue

            if row.get("trade_price") is None:
                continue

            rows.append(row)

    rows.sort(
        key=lambda x: x["trade_ts"]
    )

    return rows


def forward_return(rows, index, seconds):

    current_ts = rows[index]["trade_ts"]

    target_ts = (
        current_ts
        + seconds * 1_000_000
    )

    current_price = float(
        rows[index]["trade_price"]
    )

    if current_price <= 0:
        return None

    for j in range(index + 1, len(rows)):

        if rows[j]["trade_ts"] >= target_ts:

            future_price = float(
                rows[j]["trade_price"]
            )

            if future_price <= 0:
                return None

            return (
                future_price / current_price
            ) - 1.0

    return None


def pearson(x, y):

    if len(x) < 2:
        return None

    mx = statistics.mean(x)
    my = statistics.mean(y)

    numerator = sum(
        (a - mx) * (b - my)
        for a, b in zip(x, y)
    )

    dx = math.sqrt(
        sum(
            (a - mx) ** 2
            for a in x
        )
    )

    dy = math.sqrt(
        sum(
            (b - my) ** 2
            for b in y
        )
    )

    if dx == 0 or dy == 0:
        return None

    return numerator / (dx * dy)


def main():

    rows = load_rows()

    print("=" * 78)
    print("LARGE SESSION FORWARD RETURN RESEARCH V1")
    print("=" * 78)

    print(f"INPUT ROWS : {len(rows)}")

    for age_name, age_limit in AGE_LIMITS:

        print()
        print("=" * 78)
        print(f"BOOK AGE FILTER: {age_name}")
        print("=" * 78)

        for horizon in HORIZONS:

            returns = []
            deltas = []
            imbalance_proxy = []
            ages = []

            for i, row in enumerate(rows):

                age = row.get(
                    "book_age_us"
                )

                if age_limit is not None:

                    if age is None:
                        continue

                    if age > age_limit:
                        continue

                ret = forward_return(
                    rows,
                    i,
                    horizon
                )

                if ret is None:
                    continue

                returns.append(ret)

                deltas.append(
                    float(
                        row.get(
                            "trade_delta",
                            0.0
                        )
                    )
                )

                bid = row.get("best_bid")
                ask = row.get("best_ask")

                if bid is not None and ask is not None:

                    bid = float(bid)
                    ask = float(ask)

                    # L1 depth is not available
                    # in this feature file.
                    # This variable is therefore
                    # deliberately omitted.
                    imbalance_proxy.append(
                        ask - bid
                    )

                if age is not None:
                    ages.append(float(age))

            print()
            print(
                f"HORIZON {horizon}s"
            )

            print(
                f"N                : "
                f"{len(returns)}"
            )

            if not returns:
                continue

            print(
                f"mean return      : "
                f"{statistics.mean(returns):+.8f}"
            )

            delta_corr = pearson(
                deltas,
                returns
            )

            spread_corr = pearson(
                imbalance_proxy[:len(returns)],
                returns
            )

            print(
                f"delta correlation: "
                f"{delta_corr:+.8f}"
                if delta_corr is not None
                else "delta correlation: N/A"
            )

            print(
                f"spread correlation: "
                f"{spread_corr:+.8f}"
                if spread_corr is not None
                else "spread correlation: N/A"
            )


if __name__ == "__main__":
    main()
