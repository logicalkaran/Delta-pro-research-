import bisect
import json
import math
import statistics
from pathlib import Path


RAW = Path(
    "data/raw/research_sessions/"
    "btc_research_20260922_095821.jsonl"
)

HORIZONS = [1, 5, 10, 30]


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


def load_messages():

    messages = []

    with RAW.open() as f:

        for line in f:

            line = line.strip()

            if not line:
                continue

            record = json.loads(line)

            message = record.get("message")

            if isinstance(message, dict):
                messages.append(message)

    return messages


def build_book_states(messages):

    updates = [
        m for m in messages
        if m.get("type") == "ob_updates"
    ]

    updates.sort(
        key=lambda x: x["ts"]
    )

    asks = {}
    bids = {}

    states = []

    for message in updates:

        action = message.get("action")

        if action == "snapshot":

            asks.clear()
            bids.clear()

            for price, size in message.get("a", []):

                size = int(size)

                if size > 0:
                    asks[price] = size

            for price, size in message.get("b", []):

                size = int(size)

                if size > 0:
                    bids[price] = size

        elif action == "update":

            for price, size in message.get("a", []):

                size = int(size)

                if size == 0:
                    asks.pop(price, None)
                else:
                    asks[price] = size

            for price, size in message.get("b", []):

                size = int(size)

                if size == 0:
                    bids.pop(price, None)
                else:
                    bids[price] = size

        else:
            continue

        if len(asks) < 5 or len(bids) < 5:
            continue

        sorted_asks = sorted(
            asks.items(),
            key=lambda x: float(x[0])
        )

        sorted_bids = sorted(
            bids.items(),
            key=lambda x: float(x[0]),
            reverse=True
        )

        top_asks = sorted_asks[:5]
        top_bids = sorted_bids[:5]

        bid1 = int(top_bids[0][1])
        ask1 = int(top_asks[0][1])

        bid5 = sum(
            int(size)
            for _, size in top_bids
        )

        ask5 = sum(
            int(size)
            for _, size in top_asks
        )

        l1_den = bid1 + ask1
        l5_den = bid5 + ask5

        if l1_den <= 0 or l5_den <= 0:
            continue

        l1 = (bid1 - ask1) / l1_den
        l5 = (bid5 - ask5) / l5_den

        best_bid = float(top_bids[0][0])
        best_ask = float(top_asks[0][0])

        mid = (best_bid + best_ask) / 2.0

        states.append({
            "ts": int(message["ts"]),
            "l1": l1,
            "l5": l5,
            "depth_effect": l5 - l1,
            "mid": mid,
        })

    return states


def forward_return(states, timestamps, index, horizon):

    target = (
        states[index]["ts"]
        + horizon * 1_000_000
    )

    position = bisect.bisect_left(
        timestamps,
        target
    )

    if position >= len(states):
        return None

    current = states[index]["mid"]
    future = states[position]["mid"]

    if current <= 0:
        return None

    return (future / current) - 1.0


def main():

    messages = load_messages()

    states = build_book_states(messages)

    timestamps = [
        row["ts"]
        for row in states
    ]

    l1 = [
        row["l1"]
        for row in states
    ]

    l5 = [
        row["l5"]
        for row in states
    ]

    depth = [
        row["depth_effect"]
        for row in states
    ]

    fisher_l1 = fisher_transform(
        l1,
        period=10
    )

    fisher_l5 = fisher_transform(
        l5,
        period=10
    )

    print("=" * 78)
    print("FISHER + ORDER BOOK RESEARCH V1")
    print("=" * 78)

    print(f"BOOK STATES : {len(states)}")

    for horizon in HORIZONS:

        values = {
            "l1": [],
            "l5": [],
            "depth": [],
            "fisher_l1": [],
            "fisher_l5": [],
            "returns": [],
        }

        for i in range(len(states)):

            ret = forward_return(
                states,
                timestamps,
                i,
                horizon
            )

            if ret is None:
                continue

            values["l1"].append(l1[i])
            values["l5"].append(l5[i])
            values["depth"].append(depth[i])
            values["fisher_l1"].append(
                fisher_l1[i]
            )
            values["fisher_l5"].append(
                fisher_l5[i]
            )
            values["returns"].append(ret)

        print()
        print("=" * 78)
        print(f"HORIZON {horizon}s")
        print("=" * 78)

        print(
            f"N : {len(values['returns'])}"
        )

        for name in [
            "l1",
            "l5",
            "depth",
            "fisher_l1",
            "fisher_l5",
        ]:

            corr = pearson(
                values[name],
                values["returns"]
            )

            print(
                f"{name:12s}: "
                f"{corr:+.8f}"
            )


if __name__ == "__main__":
    main()
