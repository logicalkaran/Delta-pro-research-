import bisect
import json
import statistics
from pathlib import Path


RAW = Path(
    "data/raw/delta_btc_research_session_v2.jsonl"
)

HORIZONS = [1, 5, 10, 30]

BUCKETS = [
    ("strong_negative", float("-inf"), -0.60),
    ("negative", -0.60, -0.20),
    ("neutral", -0.20, 0.20),
    ("positive", 0.20, 0.60),
    ("strong_positive", 0.60, float("inf")),
]


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


def reconstruct_book(messages):
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

        ask_volume = sum(
            int(size)
            for _, size in top_asks
        )

        bid_volume = sum(
            int(size)
            for _, size in top_bids
        )

        denominator = bid_volume + ask_volume

        if denominator <= 0:
            continue

        imbalance = (
            (bid_volume - ask_volume)
            / denominator
        )

        best_bid = float(top_bids[0][0])
        best_ask = float(top_asks[0][0])

        mid = (best_bid + best_ask) / 2.0

        timeline.append({
            "ts": int(message["ts"]),
            "seq": int(message["seq"]),
            "best_bid": best_bid,
            "best_ask": best_ask,
            "mid": mid,
            "bid_l5": bid_volume,
            "ask_l5": ask_volume,
            "imbalance_l5": imbalance,
        })

    return timeline


def bucket_name(value):
    for name, low, high in BUCKETS:
        if low <= value < high:
            return name

    return None


def future_mid_return(timeline, timestamps, index, seconds):
    current = timeline[index]

    target = current["ts"] + seconds * 1_000_000

    position = bisect.bisect_left(
        timestamps,
        target,
    )

    if position >= len(timeline):
        return None

    current_mid = current["mid"]
    future_mid = timeline[position]["mid"]

    if current_mid <= 0:
        return None

    return (
        future_mid / current_mid
    ) - 1.0


def main():
    messages = load_messages()

    timeline = reconstruct_book(messages)

    timestamps = [
        row["ts"]
        for row in timeline
    ]

    print("=" * 78)
    print("L5 IMBALANCE → FUTURE MID-PRICE RESEARCH V1")
    print("=" * 78)

    print(f"RAW MESSAGES     : {len(messages)}")
    print(f"BOOK STATES      : {len(timeline)}")

    if not timeline:
        print("No valid order-book states.")
        return

    for horizon in HORIZONS:

        results = {
            name: []
            for name, _, _ in BUCKETS
        }

        for i, row in enumerate(timeline):

            bucket = bucket_name(
                row["imbalance_l5"]
            )

            if bucket is None:
                continue

            ret = future_mid_return(
                timeline,
                timestamps,
                i,
                horizon,
            )

            if ret is None:
                continue

            results[bucket].append(ret)

        print()
        print("=" * 78)
        print(f"HORIZON {horizon}s")
        print("=" * 78)

        for bucket, _, _ in BUCKETS:

            values = results[bucket]

            if not values:
                print(
                    f"{bucket:<18} "
                    f"N=  0 mean=N/A"
                )
                continue

            mean_return = statistics.mean(values)

            print(
                f"{bucket:<18} "
                f"N={len(values):4d} "
                f"mean={mean_return:+.8f}"
            )


if __name__ == "__main__":
    main()
