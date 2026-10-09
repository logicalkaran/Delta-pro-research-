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

FLOW_WINDOW_MS = 1000
PERSISTENCE_MS = 100

L1_THRESHOLD = 0.60
FLOW_THRESHOLD = 0.60

FRESHNESS_FILTERS = [
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

            if not row.get("mid_price_valid"):
                continue

            if not row.get("book_valid"):
                continue

            if not row.get("valid_side"):
                continue

            if row.get("l1_imbalance") is None:
                continue

            rows.append(row)

    rows.sort(
        key=lambda r: int(r["trade_ts"])
    )

    return rows


def fisher_transform(values, period=10):
    result = []

    previous_value = 0.0
    previous_fisher = 0.0

    for i, value in enumerate(values):

        start = max(
            0,
            i - period + 1
        )

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

        current = (
            0.5
            * math.log(
                (1.0 + normalized)
                / (1.0 - normalized)
            )
        )

        current = (
            0.5 * current
            + 0.5 * previous_fisher
        )

        result.append(current)

        previous_value = normalized
        previous_fisher = current

    return result


def build_flow(rows):
    timestamps = [
        int(row["trade_ts"])
        for row in rows
    ]

    result = []

    left = 0
    buy_volume = 0.0
    sell_volume = 0.0

    window_us = (
        FLOW_WINDOW_MS * 1000
    )

    for i, row in enumerate(rows):

        side = row.get("estimated_side")
        size = float(
            row.get("trade_size", 0.0)
        )

        if side == "buy":
            buy_volume += size

        elif side == "sell":
            sell_volume += size

        cutoff = (
            timestamps[i]
            - window_us
        )

        while (
            left <= i
            and timestamps[left] < cutoff
        ):

            old = rows[left]

            old_side = old.get(
                "estimated_side"
            )

            old_size = float(
                old.get("trade_size", 0.0)
            )

            if old_side == "buy":
                buy_volume -= old_size

            elif old_side == "sell":
                sell_volume -= old_size

            left += 1

        total = (
            buy_volume
            + sell_volume
        )

        if total > 0:
            value = (
                buy_volume
                - sell_volume
            ) / total
        else:
            value = 0.0

        result.append(value)

    return result


def build_persistent_flow(
    rows,
    flow,
):
    """
    Time-based persistence.

    A value is persistent when the same
    directional flow condition has remained
    active for at least PERSISTENCE_MS.
    """

    timestamps = [
        int(row["trade_ts"])
        for row in rows
    ]

    persistent = [False] * len(rows)

    persistence_us = (
        PERSISTENCE_MS * 1000
    )

    start_index = None
    direction = None

    for i, value in enumerate(flow):

        if value >= FLOW_THRESHOLD:
            current_direction = "bull"

        elif value <= -FLOW_THRESHOLD:
            current_direction = "bear"

        else:
            current_direction = None

        if (
            current_direction is None
            or current_direction != direction
        ):
            start_index = (
                i
                if current_direction is not None
                else None
            )

            direction = current_direction
            continue

        if start_index is None:
            start_index = i
            continue

        elapsed = (
            timestamps[i]
            - timestamps[start_index]
        )

        if elapsed >= persistence_us:
            persistent[i] = True

    return persistent


def future_return(
    rows,
    timestamps,
    index,
    seconds,
):
    target = (
        timestamps[index]
        + seconds * 1_000_000
    )

    j = bisect_left(
        timestamps,
        target,
        lo=index + 1,
    )

    if j >= len(rows):
        return None

    current = float(
        rows[index]["mid_price"]
    )

    future = float(
        rows[j]["mid_price"]
    )

    if current <= 0:
        return None

    return future / current - 1.0


def condition(
    l1,
    flow,
    fisher,
    persistent,
):
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
        fisher > 0
        and flow >= FLOW_THRESHOLD
    ):
        return "FISHER_BULL_FLOW"

    if (
        fisher < 0
        and flow <= -FLOW_THRESHOLD
    ):
        return "FISHER_BEAR_FLOW"

    if persistent and flow >= FLOW_THRESHOLD:
        return "PERSISTENT_BULL_FLOW"

    if persistent and flow <= -FLOW_THRESHOLD:
        return "PERSISTENT_BEAR_FLOW"

    return "OTHER"


def summarize(values):
    if not values:
        return (
            0,
            None,
            None,
            None,
        )

    mean = statistics.mean(values)
    median = statistics.median(values)

    hits = sum(
        1
        for value in values
        if value > 0
    )

    hit_rate = (
        hits / len(values)
    )

    return (
        len(values),
        mean,
        median,
        hit_rate,
    )


def print_group(
    name,
    values,
):
    n, mean, median, hit = (
        summarize(values)
    )

    if n == 0:
        print(
            f"{name:<26} N=0"
        )
        return

    print(
        f"{name:<26} "
        f"N={n:4d} "
        f"mean={mean:+.8f} "
        f"median={median:+.8f} "
        f"hit={hit:.3f}"
    )


def main():

    rows = load_rows()

    if not rows:
        print("NO VALID ROWS")
        return

    timestamps = [
        int(row["trade_ts"])
        for row in rows
    ]

    l1 = [
        float(row["l1_imbalance"])
        for row in rows
    ]

    fisher = fisher_transform(
        l1,
        period=10,
    )

    flow = build_flow(rows)

    persistent_flow = (
        build_persistent_flow(
            rows,
            flow,
        )
    )

    print("=" * 100)
    print(
        "FISHER x FLOW CONDITION RESEARCH V1"
    )
    print("=" * 100)

    print(
        f"INPUT ROWS       : {len(rows)}"
    )

    print(
        f"FLOW WINDOW      : "
        f"{FLOW_WINDOW_MS} ms"
    )

    print(
        f"PERSISTENCE      : "
        f"{PERSISTENCE_MS} ms"
    )

    print(
        f"L1 THRESHOLD     : "
        f"+/-{L1_THRESHOLD}"
    )

    print(
        f"FLOW THRESHOLD   : "
        f"+/-{FLOW_THRESHOLD}"
    )

    print()

    for age_name, age_limit in (
        FRESHNESS_FILTERS
    ):

        print("=" * 100)
        print(
            f"BOOK AGE FILTER: "
            f"{age_name}"
        )
        print("=" * 100)

        for horizon in HORIZONS:

            groups = {}

            for i, row in enumerate(rows):

                age = row.get(
                    "book_age_us"
                )

                if age_limit is not None:

                    if age is None:
                        continue

                    if float(age) > age_limit:
                        continue

                ret = future_return(
                    rows,
                    timestamps,
                    i,
                    horizon,
                )

                if ret is None:
                    continue

                name = condition(
                    l1[i],
                    flow[i],
                    fisher[i],
                    persistent_flow[i],
                )

                groups.setdefault(
                    name,
                    [],
                ).append(ret)

            print()
            print(
                f"HORIZON {horizon}s"
            )

            ordered = [
                "BULL_AGREE",
                "BEAR_AGREE",
                "FISHER_BULL_FLOW",
                "FISHER_BEAR_FLOW",
                "PERSISTENT_BULL_FLOW",
                "PERSISTENT_BEAR_FLOW",
                "OTHER",
            ]

            for name in ordered:

                print_group(
                    name,
                    groups.get(
                        name,
                        [],
                    ),
                )


if __name__ == "__main__":
    main()
