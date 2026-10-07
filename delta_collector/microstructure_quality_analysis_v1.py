import json
import statistics

INPUT_FILE = "data/processed/btc_microstructure_research_v1.jsonl"

HORIZONS = [1, 5, 10, 20]

AGE_FILTERS = {
    "all": None,
    "200ms": 200_000,
    "100ms": 100_000,
    "50ms": 50_000,
    "20ms": 20_000,
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

    if len(pairs) < 5:
        return None

    x = [p[0] for p in pairs]
    y = [p[1] for p in pairs]

    mx = statistics.mean(x)
    my = statistics.mean(y)

    numerator = sum(
        (a - mx) * (b - my)
        for a, b in pairs
    )

    denominator = (
        sum((a - mx) ** 2 for a in x)
        * sum((b - my) ** 2 for b in y)
    ) ** 0.5

    if denominator == 0:
        return None

    return numerator / denominator


def analyze(rows, horizon, max_age=None, side=None):
    xs_imbalance = []
    xs_delta = []
    ys = []

    for i, row in enumerate(rows):
        age = row.get("book_age_us")

        if max_age is not None:
            if age is None or age > max_age:
                continue

        if side is not None:
            if row.get("estimated_side") != side:
                continue

        j = i + horizon

        if j >= len(rows):
            continue

        current = safe_float(row.get("trade_price"))
        future = safe_float(rows[j].get("trade_price"))

        if current is None or future is None or current == 0:
            continue

        future_return = future / current - 1.0

        imbalance = safe_float(
            row.get("imbalance_5")
        )

        delta = safe_float(
            row.get("trade_delta")
        )

        ys.append(future_return)
        xs_imbalance.append(imbalance)
        xs_delta.append(delta)

    return {
        "n": len(ys),
        "imbalance_corr": correlation(
            xs_imbalance,
            ys
        ),
        "delta_corr": correlation(
            xs_delta,
            ys
        ),
    }


def main():
    rows = []

    with open(INPUT_FILE, "r") as f:
        for line in f:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    print("=" * 70)
    print("MICROSTRUCTURE QUALITY ANALYSIS V1")
    print("=" * 70)

    for filter_name, max_age in AGE_FILTERS.items():

        print()
        print(f"AGE FILTER: {filter_name}")
        print("-" * 70)

        for horizon in HORIZONS:
            result = analyze(
                rows,
                horizon,
                max_age=max_age
            )

            print(
                f"H{horizon:02d} "
                f"N={result['n']:3d} "
                f"imbalance={result['imbalance_corr']} "
                f"delta={result['delta_corr']}"
            )

    print()
    print("=" * 70)
    print("SIDE-CONDITIONED ANALYSIS")
    print("=" * 70)

    for side in ("buy", "sell"):

        print()
        print(f"SIDE: {side}")
        print("-" * 70)

        for horizon in HORIZONS:
            result = analyze(
                rows,
                horizon,
                max_age=100_000,
                side=side
            )

            print(
                f"H{horizon:02d} "
                f"N={result['n']:3d} "
                f"imbalance={result['imbalance_corr']} "
                f"delta={result['delta_corr']}"
            )


if __name__ == "__main__":
    main()
