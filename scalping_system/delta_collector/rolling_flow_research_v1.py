import argparse
import argparse
import json
import math
import statistics
from bisect import bisect_left
from pathlib import Path


INPUT = Path(
    "data/processed/research_sessions/"
    "btc_research_20260922_095821_canonical_features.jsonl"
)

HORIZONS = [1, 5, 10, 30]
FLOW_WINDOWS_MS = [100, 250, 500, 1000, 5000]


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
        sum((a - mx) ** 2 for a in x)
    )

    dy = math.sqrt(
        sum((b - my) ** 2 for b in y)
    )

    if dx == 0 or dy == 0:
        return None

    return numerator / (dx * dy)


def load_rows(input_path):
    rows = []

    with input_path.open() as f:
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

            rows.append(row)

    rows.sort(key=lambda r: int(r["trade_ts"]))

    return rows


def build_flow(rows, window_ms):
    """
    Calculate rolling aggressor-flow imbalance.

    flow_imbalance =
        (buy_volume - sell_volume)
        /
        (buy_volume + sell_volume)

    Window is measured in actual microseconds,
    not row count.
    """

    timestamps = [
        int(r["trade_ts"])
        for r in rows
    ]

    result = []

    left = 0
    buy_volume = 0.0
    sell_volume = 0.0

    window_us = window_ms * 1000

    for i, row in enumerate(rows):

        side = row.get("estimated_side")
        size = float(row.get("trade_size", 0.0))
        ts = timestamps[i]

        if side == "buy":
            buy_volume += size

        elif side == "sell":
            sell_volume += size

        cutoff = ts - window_us

        while left <= i and timestamps[left] < cutoff:

            old = rows[left]
            old_side = old.get("estimated_side")
            old_size = float(
                old.get("trade_size", 0.0)
            )

            if old_side == "buy":
                buy_volume -= old_size

            elif old_side == "sell":
                sell_volume -= old_size

            left += 1

        total = buy_volume + sell_volume

        if total > 0:
            imbalance = (
                (buy_volume - sell_volume)
                / total
            )
        else:
            imbalance = 0.0

        result.append(imbalance)

    return result


def future_return(rows, index, seconds):
    timestamps = [
        int(r["trade_ts"])
        for r in rows
    ]

    target = (
        timestamps[index]
        + seconds * 1_000_000
    )

    current = float(rows[index]["mid_price"])

    j = bisect_left(
        timestamps,
        target,
        lo=index + 1
    )

    if j >= len(rows):
        return None

    future = float(rows[j]["mid_price"])

    if current <= 0:
        return None

    return future / current - 1.0


def summarize(name, values, returns):
    pairs = [
        (x, y)
        for x, y in zip(values, returns)
        if x is not None and y is not None
    ]

    if len(pairs) < 2:
        print(f"{name:<32} N=0")
        return

    x = [p[0] for p in pairs]
    y = [p[1] for p in pairs]

    corr = pearson(x, y)

    print(
        f"{name:<32} "
        f"N={len(y):4d} "
        f"corr={corr:+.6f} "
        f"mean={statistics.mean(y):+.8f}"
    )


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/processed/research_sessions/btc_research_20260922_095821_canonical_features.jsonl"),
    )

    args = parser.parse_args()

    INPUT = args.input

    rows = load_rows(args.input)

    print("=" * 90)
    print("ROLLING FLOW RESEARCH V1")
    print("=" * 90)
    print(f"VALID ROWS : {len(rows)}")

    if not rows:
        return

    timestamps = [
        int(r["trade_ts"])
        for r in rows
    ]

    for window_ms in FLOW_WINDOWS_MS:

        flow = build_flow(rows, window_ms)

        print()
        print("=" * 90)
        print(f"FLOW WINDOW: {window_ms} ms")
        print("=" * 90)

        for horizon in HORIZONS:

            l1 = []
            flow_values = []
            combined = []
            returns = []

            fresh_l1 = []
            fresh_flow = []
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

                l1_value = float(
                    row["l1_imbalance"]
                )

                flow_value = flow[i]

                combined_value = (
                    l1_value * flow_value
                )

                l1.append(l1_value)
                flow_values.append(flow_value)
                combined.append(combined_value)
                returns.append(ret)

                age = row.get("book_age_us")

                if (
                    age is not None
                    and float(age) <= 50_000
                ):
                    fresh_l1.append(l1_value)
                    fresh_flow.append(flow_value)
                    fresh_combined.append(
                        combined_value
                    )
                    fresh_returns.append(ret)

            print()
            print(f"HORIZON {horizon}s")

            summarize(
                "L1",
                l1,
                returns
            )

            summarize(
                "Rolling flow",
                flow_values,
                returns
            )

            summarize(
                "L1 x rolling flow",
                combined,
                returns
            )

            print("FRESH <=50ms")

            summarize(
                "L1 fresh",
                fresh_l1,
                fresh_returns
            )

            summarize(
                "Flow fresh",
                fresh_flow,
                fresh_returns
            )

            summarize(
                "L1 x flow fresh",
                fresh_combined,
                fresh_returns
            )


if __name__ == "__main__":
    main()
