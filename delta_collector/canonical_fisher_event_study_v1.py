import json
import math
import statistics
from pathlib import Path


INPUT = Path(
    "data/processed/research_sessions/"
    "btc_research_20260922_095821_canonical_features.jsonl"
)

HORIZONS = [1, 5, 10, 30]
AGE_FILTERS = [
    ("all", None),
    ("100ms", 100_000),
    ("50ms", 50_000),
    ("20ms", 20_000),
]


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


def fisher_transform(values, period=10):

    result = []

    previous_value = 0.0
    previous_fisher = 0.0

    for i, value in enumerate(values):

        start = max(0, i - period + 1)

        window = values[start:i + 1]

        minimum = min(window)
        maximum = max(window)

        if maximum == minimum:
            normalized = previous_value
        else:
            normalized = (
                2.0
                * (
                    (value - minimum)
                    / (maximum - minimum)
                    - 0.5
                )
            )

        normalized = (
            0.33 * normalized
            + 0.67 * previous_value
        )

        normalized = max(
            -0.999,
            min(0.999, normalized)
        )

        fisher = (
            0.5
            * math.log(
                (1.0 + normalized)
                / (1.0 - normalized)
            )
        )

        fisher = (
            0.5 * fisher
            + 0.5 * previous_fisher
        )

        result.append(fisher)

        previous_value = normalized
        previous_fisher = fisher

    return result


def load_rows():

    rows = []

    with INPUT.open() as f:

        for line in f:

            line = line.strip()

            if not line:
                continue

            row = json.loads(line)

            if row.get("mid_price") is None:
                continue

            if row.get("l1_imbalance") is None:
                continue

            rows.append(row)

    rows.sort(
        key=lambda x: x["trade_ts"]
    )

    return rows


def future_return(rows, index, horizon):

    target = (
        rows[index]["trade_ts"]
        + horizon * 1_000_000
    )

    current = rows[index]["mid_price"]

    for j in range(index + 1, len(rows)):

        if rows[j]["trade_ts"] >= target:

            future = rows[j]["mid_price"]

            if current <= 0:
                return None

            return (
                future / current
            ) - 1.0

    return None


def main():

    rows = load_rows()

    l1 = [
        float(row["l1_imbalance"])
        for row in rows
    ]

    fisher = fisher_transform(
        l1,
        period=10
    )

    print("=" * 78)
    print("CANONICAL FISHER EVENT STUDY V1")
    print("=" * 78)

    print(f"INPUT ROWS : {len(rows)}")

    for age_name, age_limit in AGE_FILTERS:

        print()
        print("=" * 78)
        print(f"BOOK AGE FILTER: {age_name}")
        print("=" * 78)

        for horizon in HORIZONS:

            raw_values = []
            fisher_values = []
            returns = []

            for i, row in enumerate(rows):

                age = row.get("book_age_us")

                if age_limit is not None:

                    if age is None:
                        continue

                    if age > age_limit:
                        continue

                ret = future_return(
                    rows,
                    i,
                    horizon
                )

                if ret is None:
                    continue

                raw_values.append(l1[i])
                fisher_values.append(fisher[i])
                returns.append(ret)

            print()
            print(f"HORIZON {horizon}s")
            print(f"N             : {len(returns)}")

            if len(returns) < 2:
                continue

            raw_corr = pearson(
                raw_values,
                returns
            )

            fisher_corr = pearson(
                fisher_values,
                returns
            )

            print(
                f"L1 correlation     : "
                f"{raw_corr:+.8f}"
            )

            print(
                f"Fisher correlation : "
                f"{fisher_corr:+.8f}"
            )

    print()
    print("=" * 78)
    print("FISHER CROSSOVER EVENT STUDY")
    print("=" * 78)

    bullish = 0
    bearish = 0

    bullish_returns = {
        h: [] for h in HORIZONS
    }

    bearish_returns = {
        h: [] for h in HORIZONS
    }

    previous_fisher = None

    for i in range(1, len(rows)):

        current = fisher[i]

        if previous_fisher is None:
            previous_fisher = fisher[i - 1]
            continue

        direction = None

        if previous_fisher <= 0 < current:
            direction = "bullish"

        elif previous_fisher >= 0 > current:
            direction = "bearish"

        if direction is not None:

            if direction == "bullish":
                bullish += 1
            else:
                bearish += 1

            for horizon in HORIZONS:

                ret = future_return(
                    rows,
                    i,
                    horizon
                )

                if ret is None:
                    continue

                if direction == "bullish":
                    bullish_returns[horizon].append(ret)

                else:
                    bearish_returns[horizon].append(ret)

        previous_fisher = current

    print()
    print(f"bullish crossovers : {bullish}")
    print(f"bearish crossovers : {bearish}")

    for horizon in HORIZONS:

        b = bullish_returns[horizon]
        s = bearish_returns[horizon]

        print()
        print(f"HORIZON {horizon}s")

        if b:
            print(
                f"bullish N        : {len(b)}"
            )
            print(
                f"bullish mean     : "
                f"{statistics.mean(b):+.8f}"
            )

        if s:
            print(
                f"bearish N        : {len(s)}"
            )
            print(
                f"bearish mean     : "
                f"{statistics.mean(s):+.8f}"
            )


if __name__ == "__main__":
    main()
