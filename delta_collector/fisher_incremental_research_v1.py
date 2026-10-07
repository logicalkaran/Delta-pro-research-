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
L1_THRESHOLD = 0.60
FLOW_THRESHOLD = 0.60

FRESHNESS = [
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
        int(r["trade_ts"])
        for r in rows
    ]

    result = []

    left = 0
    buy = 0.0
    sell = 0.0

    window_us = (
        FLOW_WINDOW_MS * 1000
    )

    for i, row in enumerate(rows):

        side = row.get(
            "estimated_side"
        )

        size = float(
            row.get("trade_size", 0.0)
        )

        if side == "buy":
            buy += size
        elif side == "sell":
            sell += size

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
                buy -= old_size
            elif old_side == "sell":
                sell -= old_size

            left += 1

        total = buy + sell

        if total > 0:
            result.append(
                (buy - sell) / total
            )
        else:
            result.append(0.0)

    return result


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


def classify(
    l1,
    flow,
    fisher,
):
    """
    Mutually exclusive nested conditions.

    Positive side:
      A = L1
      B = Flow
      C = L1 + Flow
      D = Fisher + Flow
      E = Fisher + L1 + Flow

    Negative side mirrors the same structure.
    """

    if (
        l1 >= L1_THRESHOLD
        and flow >= FLOW_THRESHOLD
        and fisher > 0
    ):
        return "E_BULL_FISHER_L1_FLOW"

    if (
        l1 <= -L1_THRESHOLD
        and flow <= -FLOW_THRESHOLD
        and fisher < 0
    ):
        return "E_BEAR_FISHER_L1_FLOW"

    if (
        l1 >= L1_THRESHOLD
        and flow >= FLOW_THRESHOLD
    ):
        return "C_BULL_L1_FLOW"

    if (
        l1 <= -L1_THRESHOLD
        and flow <= -FLOW_THRESHOLD
    ):
        return "C_BEAR_L1_FLOW"

    if (
        fisher > 0
        and flow >= FLOW_THRESHOLD
    ):
        return "D_BULL_FISHER_FLOW"

    if (
        fisher < 0
        and flow <= -FLOW_THRESHOLD
    ):
        return "D_BEAR_FISHER_FLOW"

    if l1 >= L1_THRESHOLD:
        return "A_BULL_L1"

    if l1 <= -L1_THRESHOLD:
        return "A_BEAR_L1"

    if flow >= FLOW_THRESHOLD:
        return "B_BULL_FLOW"

    if flow <= -FLOW_THRESHOLD:
        return "B_BEAR_FLOW"

    return "OTHER"


def summarize(values):
    if not values:
        return None

    return {
        "n": len(values),
        "mean": statistics.mean(values),
        "median": statistics.median(values),
        "hit": (
            sum(x > 0 for x in values)
            / len(values)
        ),
    }


def print_summary(name, values):
    result = summarize(values)

    if result is None:
        print(
            f"{name:<30} N=0"
        )
        return

    print(
        f"{name:<30} "
        f"N={result['n']:4d} "
        f"mean={result['mean']:+.8f} "
        f"median={result['median']:+.8f} "
        f"hit={result['hit']:.3f}"
    )


def main():

    rows = load_rows()

    timestamps = [
        int(r["trade_ts"])
        for r in rows
    ]

    l1 = [
        float(r["l1_imbalance"])
        for r in rows
    ]

    fisher = fisher_transform(l1)

    flow = build_flow(rows)

    print("=" * 100)
    print("FISHER INCREMENTAL INFORMATION RESEARCH V1")
    print("=" * 100)

    print(
        f"ROWS             : {len(rows)}"
    )
    print(
        f"FLOW WINDOW      : {FLOW_WINDOW_MS} ms"
    )
    print(
        f"L1 THRESHOLD     : +/-{L1_THRESHOLD}"
    )
    print(
        f"FLOW THRESHOLD   : +/-{FLOW_THRESHOLD}"
    )

    for age_name, age_limit in FRESHNESS:

        print()
        print("=" * 100)
        print(
            f"BOOK AGE FILTER: {age_name}"
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

                name = classify(
                    l1[i],
                    flow[i],
                    fisher[i],
                )

                groups.setdefault(
                    name,
                    [],
                ).append(ret)

            print()
            print(
                f"HORIZON {horizon}s"
            )

            order = [
                "A_BULL_L1",
                "A_BEAR_L1",
                "B_BULL_FLOW",
                "B_BEAR_FLOW",
                "C_BULL_L1_FLOW",
                "C_BEAR_L1_FLOW",
                "D_BULL_FISHER_FLOW",
                "D_BEAR_FISHER_FLOW",
                "E_BULL_FISHER_L1_FLOW",
                "E_BEAR_FISHER_L1_FLOW",
                "OTHER",
            ]

            for name in order:
                print_summary(
                    name,
                    groups.get(
                        name,
                        [],
                    ),
                )


if __name__ == "__main__":
    main()
