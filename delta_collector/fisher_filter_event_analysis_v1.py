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

FLOW_WINDOW_US = 1_000_000
L1_THRESHOLD = 0.60
FLOW_THRESHOLD = 0.60


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

            if row.get("mid_price") is None:
                continue

            rows.append(row)

    rows.sort(key=lambda x: int(x["trade_ts"]))

    return rows


def fisher_transform(values, period=10):
    result = []

    previous_raw = 0.0
    previous_fisher = 0.0

    for i, value in enumerate(values):

        start = max(0, i - period + 1)
        window = values[start:i + 1]

        lo = min(window)
        hi = max(window)

        if hi == lo:
            raw = previous_raw
        else:
            raw = 2.0 * (
                (value - lo) / (hi - lo) - 0.5
            )

        raw = (
            0.33 * raw
            + 0.67 * previous_raw
        )

        raw = max(-0.999, min(0.999, raw))

        current = (
            0.5
            * math.log(
                (1.0 + raw)
                / (1.0 - raw)
            )
        )

        current = (
            0.5 * current
            + 0.5 * previous_fisher
        )

        result.append(current)

        previous_raw = raw
        previous_fisher = current

    return result


def build_flow(rows):
    result = []

    timestamps = [
        int(row["trade_ts"])
        for row in rows
    ]

    left = 0
    buy = 0.0
    sell = 0.0

    for i, row in enumerate(rows):

        side = row.get("estimated_side")
        size = float(row.get("trade_size", 0.0))

        if side == "buy":
            buy += size

        elif side == "sell":
            sell += size

        cutoff = (
            timestamps[i]
            - FLOW_WINDOW_US
        )

        while (
            left <= i
            and timestamps[left] < cutoff
        ):

            old = rows[left]
            old_side = old.get("estimated_side")
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


def base_state(l1, flow):

    if (
        l1 >= L1_THRESHOLD
        and flow >= FLOW_THRESHOLD
    ):
        return "bullish"

    if (
        l1 <= -L1_THRESHOLD
        and flow <= -FLOW_THRESHOLD
    ):
        return "bearish"

    return None


def classify_event(
    l1,
    flow,
    fisher,
):
    state = base_state(l1, flow)

    if state is None:
        return None

    if state == "bullish":
        fisher_agrees = fisher > 0
    else:
        fisher_agrees = fisher < 0

    if fisher_agrees:
        return (
            state,
            "fisher_agrees"
        )

    return (
        state,
        "fisher_rejects"
    )


def find_events(
    rows,
    flow,
    fisher,
    age_limit,
):
    events = []
    active = None

    for i, row in enumerate(rows):

        age = row.get("book_age_us")

        if (
            age_limit is not None
            and (
                age is None
                or float(age) > age_limit
            )
        ):
            state = None

        else:

            state = classify_event(
                float(row["l1_imbalance"]),
                flow[i],
                fisher[i],
            )

        if state is not None:

            direction = state[0]

            if active is None:

                events.append({
                    "index": i,
                    "direction": direction,
                    "classification": state[1],
                })

                active = direction

            elif direction != active:

                events.append({
                    "index": i,
                    "direction": direction,
                    "classification": state[1],
                })

                active = direction

        else:

            active = None

    return events


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


def print_stats(label, values):

    if not values:
        print(f"{label:<30} N=0")
        return

    print(
        f"{label:<30} "
        f"N={len(values):3d} "
        f"mean={statistics.mean(values):+.8f} "
        f"median={statistics.median(values):+.8f} "
        f"hit={sum(v > 0 for v in values)/len(values):.3f}"
    )


def main():

    rows = load_rows()

    timestamps = [
        int(row["trade_ts"])
        for row in rows
    ]

    l1 = [
        float(row["l1_imbalance"])
        for row in rows
    ]

    flow = build_flow(rows)
    fisher = fisher_transform(l1)

    print("=" * 100)
    print(
        "FISHER FILTER EVENT ANALYSIS V1"
    )
    print("=" * 100)

    for age_name, age_limit in [
        ("all", None),
        ("100ms", 100_000),
        ("50ms", 50_000),
    ]:

        events = find_events(
            rows,
            flow,
            fisher,
            age_limit,
        )

        print()
        print("=" * 100)
        print(f"BOOK AGE: {age_name}")
        print("=" * 100)

        for direction in [
            "bullish",
            "bearish",
        ]:

            print()
            print(
                f"{direction.upper()} "
                "L1 + FLOW EVENTS"
            )

            for classification in [
                "fisher_agrees",
                "fisher_rejects",
            ]:

                subset = [
                    event
                    for event in events
                    if (
                        event["direction"]
                        == direction
                        and event["classification"]
                        == classification
                    )
                ]

                print()
                print(
                    f"{classification}: "
                    f"events={len(subset)}"
                )

                for horizon in HORIZONS:

                    returns = []

                    for event in subset:

                        ret = future_return(
                            rows,
                            timestamps,
                            event["index"],
                            horizon,
                        )

                        if ret is not None:
                            returns.append(ret)

                    print_stats(
                        f"  {horizon}s",
                        returns,
                    )


if __name__ == "__main__":
    main()
