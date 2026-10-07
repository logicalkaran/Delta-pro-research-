import json
import statistics
import bisect

INPUT_FILE = "data/processed/btc_microstructure_features_v1.jsonl"

HORIZONS_US = {
    "1s": 1_000_000,
    "5s": 5_000_000,
    "10s": 10_000_000,
    "30s": 30_000_000,
}


def safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def correlation(xs, ys):
    pairs = [
        (x, y)
        for x, y in zip(xs, ys)
        if x is not None and y is not None
    ]

    if len(pairs) < 10:
        return None

    xs = [x for x, _ in pairs]
    ys = [y for _, y in pairs]

    mx = statistics.mean(xs)
    my = statistics.mean(ys)

    numerator = sum(
        (x - mx) * (y - my)
        for x, y in pairs
    )

    denominator = (
        sum((x - mx) ** 2 for x in xs)
        * sum((y - my) ** 2 for y in ys)
    ) ** 0.5

    if denominator == 0:
        return None

    return numerator / denominator


def main():
    rows = []

    with open(INPUT_FILE, "r") as f:
        for line in f:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    rows.sort(
        key=lambda x: int(x.get("trade_ts", 0))
    )

    timestamps = [
        int(row["trade_ts"])
        for row in rows
    ]

    prices = [
        safe_float(row.get("trade_price"))
        for row in rows
    ]

    print("=" * 70)
    print("TIME-HORIZON MICROSTRUCTURE RESEARCH V1")
    print("=" * 70)

    for name, horizon_us in HORIZONS_US.items():

        imbalance_values = []
        delta_values = []
        returns = []

        for i, row in enumerate(rows):

            ts = timestamps[i]
            target_ts = ts + horizon_us

            j = bisect.bisect_left(
                timestamps,
                target_ts,
                lo=i + 1
            )

            if j >= len(rows):
                continue

            current_price = prices[i]
            future_price = prices[j]

            if (
                current_price is None
                or future_price is None
                or current_price == 0
            ):
                continue

            future_return = (
                future_price / current_price
                - 1.0
            )

            imbalance = safe_float(
                row.get("imbalance_5")
            )

            delta = safe_float(
                row.get("trade_delta")
            )

            returns.append(future_return)
            imbalance_values.append(imbalance)
            delta_values.append(delta)

        print()
        print(f"HORIZON {name}")
        print("-" * 70)
        print(f"observations          : {len(returns)}")

        if returns:
            print(
                f"mean forward return   : "
                f"{statistics.mean(returns):.8f}"
            )

        print(
            f"imbalance correlation : "
            f"{correlation(imbalance_values, returns)}"
        )

        print(
            f"delta correlation     : "
            f"{correlation(delta_values, returns)}"
        )


if __name__ == "__main__":
    main()
