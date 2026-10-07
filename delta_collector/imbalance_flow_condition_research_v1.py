import argparse
import json
import statistics
from bisect import bisect_left
from pathlib import Path


INPUT = Path(
    "data/processed/research_sessions/"
    "btc_research_20260922_095821_canonical_features.jsonl"
)

HORIZONS = [1, 5, 10, 30]

FLOW_WINDOW_MS = 1000

L1_THRESHOLD = 0.60
FLOW_THRESHOLD = 0.60


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

            if row.get("l1_imbalance") is None:
                continue

            rows.append(row)

    rows.sort(key=lambda r: int(r["trade_ts"]))

    return rows


def build_flow(rows):
    timestamps = [
        int(r["trade_ts"])
        for r in rows
    ]

    flow = []

    left = 0
    buy_volume = 0.0
    sell_volume = 0.0

    window_us = FLOW_WINDOW_MS * 1000

    for i, row in enumerate(rows):

        side = row.get("estimated_side")
        size = float(row.get("trade_size", 0.0))

        if side == "buy":
            buy_volume += size

        elif side == "sell":
            sell_volume += size

        cutoff = timestamps[i] - window_us

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
            value = (
                (buy_volume - sell_volume)
                / total
            )
        else:
            value = 0.0

        flow.append(value)

    return flow


def future_return(rows, timestamps, index, seconds):
    target = (
        timestamps[index]
        + seconds * 1_000_000
    )

    j = bisect_left(
        timestamps,
        target,
        lo=index + 1
    )

    if j >= len(rows):
        return None

    current = float(rows[index]["mid_price"])
    future = float(rows[j]["mid_price"])

    if current <= 0:
        return None

    return future / current - 1.0


def bucket(l1, flow):
    if (
        l1 >= L1_THRESHOLD
        and flow >= FLOW_THRESHOLD
    ):
        return "BULL_AGREE"

    if (
        l1 <= -L1_THRESHOLD
        and flow <= -FLOW_THRESHOLD
    ):
        return "BEAR_AGREE"

    if (
        l1 >= L1_THRESHOLD
        and flow <= -FLOW_THRESHOLD
    ):
        return "BULL_DIVERGE"

    if (
        l1 <= -L1_THRESHOLD
        and flow >= FLOW_THRESHOLD
    ):
        return "BEAR_DIVERGE"

    return "OTHER"


def summarize(values):
    if not values:
        return (
            0,
            None,
            None,
            None
        )

    mean = statistics.mean(values)
    median = statistics.median(values)

    hits = sum(
        1
        for x in values
        if x > 0
    )

    hit_rate = hits / len(values)

    return (
        len(values),
        mean,
        median,
        hit_rate
    )


def print_group(name, values):
    n, mean, median, hit_rate = summarize(values)

    if n == 0:
        print(
            f"{name:<20} N=0"
        )
        return

    print(
        f"{name:<20} "
        f"N={n:4d} "
        f"mean={mean:+.8f} "
        f"median={median:+.8f} "
        f"hit={hit_rate:.3f}"
    )


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--input",
        type=Path,
        default=Path(
            "data/processed/research_sessions/"
            "btc_research_20260922_095821_canonical_features.jsonl"
        ),
    )

    args = parser.parse_args()

    rows = load_rows(args.input)
    timestamps = [
        int(r["trade_ts"])
        for r in rows
    ]

    flow = build_flow(rows)

    print("=" * 90)
    print("IMBALANCE + FLOW CONDITION RESEARCH V1")
    print("=" * 90)

    print(f"ROWS             : {len(rows)}")
    print(f"FLOW WINDOW      : {FLOW_WINDOW_MS} ms")
    print(f"L1 THRESHOLD     : ±{L1_THRESHOLD}")
    print(f"FLOW THRESHOLD   : ±{FLOW_THRESHOLD}")

    for horizon in HORIZONS:

        groups = {
            "BULL_AGREE": [],
            "BEAR_AGREE": [],
            "BULL_DIVERGE": [],
            "BEAR_DIVERGE": [],
            "OTHER": [],
        }

        fresh_groups = {
            "BULL_AGREE": [],
            "BEAR_AGREE": [],
            "BULL_DIVERGE": [],
            "BEAR_DIVERGE": [],
            "OTHER": [],
        }

        for i, row in enumerate(rows):

            ret = future_return(
                rows,
                timestamps,
                i,
                horizon
            )

            if ret is None:
                continue

            l1 = float(
                row["l1_imbalance"]
            )

            f = flow[i]

            group = bucket(l1, f)

            groups[group].append(ret)

            age = row.get("book_age_us")

            if (
                age is not None
                and float(age) <= 50_000
            ):
                fresh_groups[group].append(ret)

        print()
        print("=" * 90)
        print(f"HORIZON {horizon}s")
        print("=" * 90)

        print("ALL")

        for name in groups:
            print_group(
                name,
                groups[name]
            )

        print()
        print("FRESH BOOK <=50ms")

        for name in fresh_groups:
            print_group(
                name,
                fresh_groups[name]
            )


if __name__ == "__main__":
    main()
