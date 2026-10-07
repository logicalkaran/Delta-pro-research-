import bisect
import json
import math
import statistics
from pathlib import Path


RAW = Path(
    "data/raw/delta_btc_research_session_v2.jsonl"
)

HORIZONS = [1, 5, 10, 30]


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


def pearson(x, y):
    if len(x) != len(y) or len(x) < 2:
        return None

    mx = statistics.mean(x)
    my = statistics.mean(y)

    numerator = sum(
        (a - mx) * (b - my)
        for a, b in zip(x, y)
    )

    den_x = math.sqrt(
        sum((a - mx) ** 2 for a in x)
    )

    den_y = math.sqrt(
        sum((b - my) ** 2 for b in y)
    )

    if den_x == 0 or den_y == 0:
        return None

    return numerator / (den_x * den_y)


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

            for p, s in message.get("a", []):
                s = int(s)

                if s > 0:
                    asks[p] = s

            for p, s in message.get("b", []):
                s = int(s)

                if s > 0:
                    bids[p] = s

        elif action == "update":

            for p, s in message.get("a", []):
                s = int(s)

                if s == 0:
                    asks.pop(p, None)
                else:
                    asks[p] = s

            for p, s in message.get("b", []):
                s = int(s)

                if s == 0:
                    bids.pop(p, None)
                else:
                    bids[p] = s

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

        l1_bid = int(top_bids[0][1])
        l1_ask = int(top_asks[0][1])

        l1_den = l1_bid + l1_ask

        if l1_den <= 0:
            continue

        l1 = (
            (l1_bid - l1_ask)
            / l1_den
        )

        l5_bid = sum(
            int(size)
            for _, size in top_bids
        )

        l5_ask = sum(
            int(size)
            for _, size in top_asks
        )

        l5_den = l5_bid + l5_ask

        if l5_den <= 0:
            continue

        l5 = (
            (l5_bid - l5_ask)
            / l5_den
        )

        best_bid = float(top_bids[0][0])
        best_ask = float(top_asks[0][0])

        mid = (best_bid + best_ask) / 2.0

        timeline.append({
            "ts": int(message["ts"]),
            "l1": l1,
            "l5": l5,
            "mid": mid,
        })

    return timeline


def future_return(timeline, timestamps, i, seconds):
    target = (
        timeline[i]["ts"]
        + seconds * 1_000_000
    )

    pos = bisect.bisect_left(
        timestamps,
        target
    )

    if pos >= len(timeline):
        return None

    current_mid = timeline[i]["mid"]
    future_mid = timeline[pos]["mid"]

    if current_mid <= 0:
        return None

    return (
        future_mid / current_mid
    ) - 1.0


def quantile_bucket(value, values):
    ordered = sorted(values)

    n = len(ordered)

    if n < 5:
        return None

    rank = sum(
        1 for x in ordered
        if x <= value
    ) / n

    if rank <= 0.20:
        return "Q1"

    if rank <= 0.40:
        return "Q2"

    if rank <= 0.60:
        return "Q3"

    if rank <= 0.80:
        return "Q4"

    return "Q5"


def main():
    messages = load_messages()
    timeline = build_timeline(messages)

    timestamps = [
        row["ts"]
        for row in timeline
    ]

    print("=" * 78)
    print("L1 vs L5 CONTINUOUS MICROSTRUCTURE RESEARCH V1")
    print("=" * 78)

    print(f"BOOK STATES : {len(timeline)}")

    l1 = [row["l1"] for row in timeline]
    l5 = [row["l5"] for row in timeline]

    differences = [
        abs(a - b)
        for a, b in zip(l1, l5)
    ]

    print()
    print("L1 ↔ L5")
    print("-" * 78)
    print(f"correlation      : {pearson(l1, l5):+.8f}")
    print(
        f"mean abs diff    : "
        f"{statistics.mean(differences):.8f}"
    )
    print(
        f"max abs diff     : "
        f"{max(differences):.8f}"
    )

    for horizon in HORIZONS:

        returns = []
        l1_values = []
        l5_values = []

        for i in range(len(timeline)):

            ret = future_return(
                timeline,
                timestamps,
                i,
                horizon
            )

            if ret is None:
                continue

            returns.append(ret)
            l1_values.append(timeline[i]["l1"])
            l5_values.append(timeline[i]["l5"])

        print()
        print("=" * 78)
        print(f"HORIZON {horizon}s")
        print("=" * 78)

        print(f"observations      : {len(returns)}")
        print(
            f"L1 correlation    : "
            f"{pearson(l1_values, returns):+.8f}"
        )
        print(
            f"L5 correlation    : "
            f"{pearson(l5_values, returns):+.8f}"
        )

        buckets = {
            "Q1": [],
            "Q2": [],
            "Q3": [],
            "Q4": [],
            "Q5": [],
        }

        for value, ret in zip(l5_values, returns):

            bucket = quantile_bucket(
                value,
                l5_values
            )

            if bucket:
                buckets[bucket].append(ret)

        print()
        print("L5 QUINTILES")

        for bucket in ["Q1", "Q2", "Q3", "Q4", "Q5"]:

            values = buckets[bucket]

            if not values:
                print(
                    f"{bucket} "
                    f"N=0 mean=N/A"
                )
                continue

            print(
                f"{bucket} "
                f"N={len(values):3d} "
                f"mean={statistics.mean(values):+.8f}"
            )


if __name__ == "__main__":
    main()
