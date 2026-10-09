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

FRESHNESS_FILTERS = [
    ("all", None),
    ("100ms", 100_000),
    ("50ms", 50_000),
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
    buy_volume = 0.0
    sell_volume = 0.0

    window_us = FLOW_WINDOW_MS * 1000

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
            result.append(
                (
                    buy_volume
                    - sell_volume
                ) / total
            )
        else:
            result.append(0.0)

    return result


def future_return(
    rows,
    timestamps,
    index,
    horizon,
):
    target = (
        timestamps[index]
        + horizon * 1_000_000
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


def event_state(
    l1,
    flow,
    fisher,
):
    bullish = (
        l1 >= L1_THRESHOLD
        and flow >= FLOW_THRESHOLD
        and fisher > 0
    )

    bearish = (
        l1 <= -L1_THRESHOLD
        and flow <= -FLOW_THRESHOLD
        and fisher < 0
    )

    if bullish:
        return "bullish"

    if bearish:
        return "bearish"

    return None


def find_nonoverlapping_events(
    rows,
    fisher,
    flow,
    age_limit,
):
    events = []

    active = None

    for i, row in enumerate(rows):

        age = row.get("book_age_us")

        if age_limit is not None:

            if age is None:
                state = None
            elif float(age) > age_limit:
                state = None
            else:
                state = event_state(
                    float(row["l1_imbalance"]),
                    flow[i],
                    fisher[i],
                )
        else:
            state = event_state(
                float(row["l1_imbalance"]),
                flow[i],
                fisher[i],
            )

        # Rising edge: create one event.
        if state is not None and active is None:

            events.append({
                "index": i,
                "side": state,
                "timestamp": int(
                    row["trade_ts"]
                ),
            })

            active = state

        # Condition ended or changed side:
        # re-arm detector.
        elif state is None:
            active = None

        elif state != active:
            events.append({
                "index": i,
                "side": state,
                "timestamp": int(
                    row["trade_ts"]
                ),
            })

            active = state

    return events


def summarize(values):
    if not values:
        return None

    return {
        "n": len(values),
        "mean": statistics.mean(values),
        "median": statistics.median(values),
        "hit": (
            sum(
                value > 0
                for value in values
            )
            / len(values)
        ),
    }


def print_summary(name, values):
    result = summarize(values)

    if result is None:
        print(
            f"{name:<26} N=0"
        )
        return

    print(
        f"{name:<26} "
        f"N={result['n']:3d} "
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
    print(
        "NON-OVERLAPPING FISHER + L1 + FLOW "
        "EVENT RESEARCH V1"
    )
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

    for age_name, age_limit in FRESHNESS_FILTERS:

        events = find_nonoverlapping_events(
            rows,
            fisher,
            flow,
            age_limit,
        )

        bullish = [
            event
            for event in events
            if event["side"] == "bullish"
        ]

        bearish = [
            event
            for event in events
            if event["side"] == "bearish"
        ]

        print()
        print("=" * 100)
        print(
            f"BOOK AGE: {age_name}"
        )
        print("=" * 100)

        print(
            f"TOTAL EVENTS : {len(events)}"
        )

        print(
            f"BULLISH      : {len(bullish)}"
        )

        print(
            f"BEARISH      : {len(bearish)}"
        )

        for horizon in HORIZONS:

            bull_returns = []
            bear_returns = []

            for event in bullish:

                ret = future_return(
                    rows,
                    timestamps,
                    event["index"],
                    horizon,
                )

                if ret is not None:
                    bull_returns.append(ret)

            for event in bearish:

                ret = future_return(
                    rows,
                    timestamps,
                    event["index"],
                    horizon,
                )

                if ret is not None:
                    bear_returns.append(ret)

            print()
            print(
                f"HORIZON {horizon}s"
            )

            print_summary(
                "BULLISH EVENTS",
                bull_returns,
            )

            print_summary(
                "BEARISH EVENTS",
                bear_returns,
            )


if __name__ == "__main__":
    main()
