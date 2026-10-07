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


def build_timeline(messages):
    updates = [
        m for m in messages
        if m.get("type") == "ob_updates"
    ]

    updates.sort(key=lambda x: x["ts"])

    asks = {}
    bids = {}

    timeline = []

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

        bid_l1 = int(top_bids[0][1])
        ask_l1 = int(top_asks[0][1])

        bid_l5 = sum(
            int(size)
            for _, size in top_bids
        )

        ask_l5 = sum(
            int(size)
            for _, size in top_asks
        )

        l1_den = bid_l1 + ask_l1
        l5_den = bid_l5 + ask_l5

        if l1_den <= 0 or l5_den <= 0:
            continue

        l1 = (
            (bid_l1 - ask_l1)
            / l1_den
        )

        l5 = (
            (bid_l5 - ask_l5)
            / l5_den
        )

        best_bid = float(top_bids[0][0])
        best_ask = float(top_asks[0][0])

        timeline.append({
            "ts": int(message["ts"]),
            "l1": l1,
            "l5": l5,
            "mid": (best_bid + best_ask) / 2.0,
        })

    return timeline


def future_return(timeline, timestamps, index, horizon):
    target = (
        timeline[index]["ts"]
        + horizon * 1_000_000
    )

    pos = bisect.bisect_left(
        timestamps,
        target
    )

    if pos >= len(timeline):
        return None

    current = timeline[index]["mid"]
    future = timeline[pos]["mid"]

    if current <= 0:
        return None

    return (future / current) - 1.0


def main():
    messages = load_messages()
    timeline = build_timeline(messages)

    timestamps = [
        row["ts"]
        for row in timeline
    ]

    print("=" * 78)
    print("LARGE SESSION L1 vs L5 IMBALANCE RESEARCH V1")
    print("=" * 78)

    print(f"BOOK STATES : {len(timeline)}")

    l1 = [x["l1"] for x in timeline]
    l5 = [x["l5"] for x in timeline]

    differences = [
        abs(a - b)
        for a, b in zip(l1, l5)
    ]

    print()
    print("L1 vs L5")
    print("-" * 78)
    print(
        f"correlation   : "
        f"{pearson(l1, l5):+.8f}"
    )
    print(
        f"mean abs diff : "
        f"{statistics.mean(differences):.8f}"
    )
    print(
        f"max abs diff  : "
        f"{max(differences):.8f}"
    )

    for horizon in HORIZONS:

        l1_values = []
        l5_values = []
        returns = []

        for i in range(len(timeline)):

            ret = future_return(
                timeline,
                timestamps,
                i,
                horizon
            )

            if ret is None:
                continue

            l1_values.append(
                timeline[i]["l1"]
            )

            l5_values.append(
                timeline[i]["l5"]
            )

            returns.append(ret)

        print()
        print("=" * 78)
        print(f"HORIZON {horizon}s")
        print("=" * 78)

        print(
            f"observations : "
            f"{len(returns)}"
        )

        print(
            f"L1 correlation : "
            f"{pearson(l1_values, returns):+.8f}"
        )

        print(
            f"L5 correlation : "
            f"{pearson(l5_values, returns):+.8f}"
        )


if __name__ == "__main__":
    main()
