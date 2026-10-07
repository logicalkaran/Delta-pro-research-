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

FLOW_WINDOW_US = 1_000_000

L1_THRESHOLD = 0.60
FLOW_THRESHOLD = 0.60

FRESHNESS_FILTERS = [
    ("all", None),
    ("100ms", 100_000),
    ("50ms", 50_000),
]


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

        fisher = (
            0.5
            * math.log(
                (1.0 + raw) /
                (1.0 - raw)
            )
        )

        fisher = (
            0.5 * fisher
            + 0.5 * previous_fisher
        )

        result.append(fisher)

        previous_raw = raw
        previous_fisher = fisher

    return result


def build_flow(rows):
    flow = []

    left = 0
    buy_volume = 0.0
    sell_volume = 0.0

    timestamps = [
        int(row["trade_ts"])
        for row in rows
    ]

    for i, row in enumerate(rows):

        side = row.get("estimated_side")
        size = float(row.get("trade_size", 0.0))

        if side == "buy":
            buy_volume += size

        elif side == "sell":
            sell_volume += size

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
                buy_volume -= old_size

            elif old_side == "sell":
                sell_volume -= old_size

            left += 1

        total = buy_volume + sell_volume

        if total > 0:
            flow.append(
                (buy_volume - sell_volume) / total
            )
        else:
            flow.append(0.0)

    return flow


def state_l1_flow(l1, flow):
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


def state_fisher_l1_flow(l1, flow, fisher):
    if (
        l1 >= L1_THRESHOLD
        and flow >= FLOW_THRESHOLD
        and fisher > 0
    ):
        return "bullish"

    if (
        l1 <= -L1_THRESHOLD
        and flow <= -FLOW_THRESHOLD
        and fisher < 0
    ):
        return "bearish"

    return None


def find_events(
    rows,
    state_function,
    fisher=None,
    age_limit=None,
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
            l1 = float(row["l1_imbalance"])

            if fisher is None:
                state = state_function(
                    l1,
                    flow_values[i],
                )
            else:
                state = state_function(
                    l1,
                    flow_values[i],
                    fisher[i],
                )

        if state is not None and active is None:

            events.append({
                "index": i,
                "side": state,
            })

            active = state

        elif state is None:

            active = None

        elif state != active:

            events.append({
                "index": i,
                "side": state,
            })

            active = state

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


def stats(values):
    if not values:
        return None

    return (
        len(values),
        statistics.mean(values),
        statistics.median(values),
        sum(v > 0 for v in values) / len(values),
    )


def print_result(label, values):
    result = stats(values)

    if result is None:
        print(f"{label:<28} N=0")
        return

    n, mean, median, hit = result

    print(
        f"{label:<28} "
        f"N={n:3d} "
        f"mean={mean:+.8f} "
        f"median={median:+.8f} "
        f"hit={hit:.3f}"
    )


def main():

    global flow_values

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--input",
        type=Path,
        default=INPUT,
    )

    args = parser.parse_args()

    rows = load_rows(args.input)

    timestamps = [
        int(row["trade_ts"])
        for row in rows
    ]

    l1_values = [
        float(row["l1_imbalance"])
        for row in rows
    ]

    flow_values = build_flow(rows)
    fisher_values = fisher_transform(
        l1_values
    )

    print("=" * 100)
    print(
        "NON-OVERLAPPING INCREMENTAL "
        "L1 + FLOW vs FISHER + L1 + FLOW"
    )
    print("=" * 100)

    print(f"ROWS            : {len(rows)}")
    print(f"FLOW WINDOW     : 1000 ms")
    print(f"L1 THRESHOLD    : +/-{L1_THRESHOLD}")
    print(f"FLOW THRESHOLD  : +/-{FLOW_THRESHOLD}")

    for age_name, age_limit in FRESHNESS_FILTERS:

        l1_flow_events = find_events(
            rows,
            state_l1_flow,
            fisher=None,
            age_limit=age_limit,
        )

        fisher_events = find_events(
            rows,
            state_fisher_l1_flow,
            fisher=fisher_values,
            age_limit=age_limit,
        )

        print()
        print("=" * 100)
        print(f"BOOK AGE: {age_name}")
        print("=" * 100)

        for horizon in HORIZONS:

            print()
            print(f"HORIZON {horizon}s")

            for name, events in [
                (
                    "L1 + FLOW",
                    l1_flow_events,
                ),
                (
                    "FISHER + L1 + FLOW",
                    fisher_events,
                ),
            ]:

                bullish = []
                bearish = []

                for event in events:

                    ret = future_return(
                        rows,
                        timestamps,
                        event["index"],
                        horizon,
                    )

                    if ret is None:
                        continue

                    if event["side"] == "bullish":
                        bullish.append(ret)
                    else:
                        bearish.append(ret)

                print(
                    f"{name}: "
                    f"events={len(events)} "
                    f"bull={sum(e['side']=='bullish' for e in events)} "
                    f"bear={sum(e['side']=='bearish' for e in events)}"
                )

                print_result(
                    "  bullish",
                    bullish,
                )

                print_result(
                    "  bearish",
                    bearish,
                )


if __name__ == "__main__":
    main()
