import json
import statistics

INPUT_FILE = "data/processed/btc_microstructure_features_v1.jsonl"
OUTPUT_FILE = "data/processed/btc_microstructure_research_v1.jsonl"

HORIZONS = [1, 5, 10, 20]


def safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def correlation(x, y):
    pairs = [
        (a, b)
        for a, b in zip(x, y)
        if a is not None and b is not None
    ]

    if len(pairs) < 3:
        return None

    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]

    mx = statistics.mean(xs)
    my = statistics.mean(ys)

    numerator = sum(
        (a - mx) * (b - my)
        for a, b in pairs
    )

    den_x = sum((a - mx) ** 2 for a in xs)
    den_y = sum((b - my) ** 2 for b in ys)

    denominator = (den_x * den_y) ** 0.5

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

    prices = [
        safe_float(row.get("trade_price"))
        for row in rows
    ]

    for i, row in enumerate(rows):
        current_price = prices[i]

        for horizon in HORIZONS:
            j = i + horizon

            if (
                current_price is None
                or j >= len(rows)
                or prices[j] is None
                or current_price == 0
            ):
                row[f"return_{horizon}"] = None
            else:
                row[f"return_{horizon}"] = (
                    prices[j] / current_price - 1.0
                )

        row["delta_signal"] = safe_float(
            row.get("trade_delta")
        )

        row["imbalance_signal"] = safe_float(
            row.get("imbalance_5")
        )

    with open(OUTPUT_FILE, "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")

    print("=" * 60)
    print("MICROSTRUCTURE RESEARCH V1")
    print("=" * 60)

    print()
    print(f"rows                  : {len(rows)}")

    for horizon in HORIZONS:
        returns = [
            row[f"return_{horizon}"]
            for row in rows
            if row[f"return_{horizon}"] is not None
        ]

        deltas = [
            row["delta_signal"]
            for row in rows
            if row["return_%d" % horizon] is not None
            and row["delta_signal"] is not None
        ]

        imbalances = [
            row["imbalance_signal"]
            for row in rows
            if row["return_%d" % horizon] is not None
            and row["imbalance_signal"] is not None
        ]

        print()
        print(f"HORIZON {horizon}")
        print("-" * 60)
        print(f"observations          : {len(returns)}")

        if returns:
            print(
                f"mean return           : "
                f"{statistics.mean(returns):.8f}"
            )

        print(
            f"delta/return corr     : "
            f"{correlation(deltas, returns)}"
        )

        print(
            f"imbalance/return corr : "
            f"{correlation(imbalances, returns)}"
        )

    print()
    print(f"output                : {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
