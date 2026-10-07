import bisect
import json
import sys
from pathlib import Path


if len(sys.argv) != 2:
    print(
        "Usage:\n"
        "python -m delta_collector.synchronize_large_session_v1 "
        "<jsonl_file>"
    )
    raise SystemExit(1)


INPUT = Path(sys.argv[1])

OUTPUT_DIR = Path("data/processed/research_sessions")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT = OUTPUT_DIR / (
    INPUT.stem + "_synchronized.jsonl"
)


def load_records():
    trades = []
    updates = []

    with INPUT.open() as f:
        for line in f:

            line = line.strip()

            if not line:
                continue

            record = json.loads(line)
            message = record.get("message")

            if not isinstance(message, dict):
                continue

            message_type = message.get("type")

            if message_type == "trades":
                trades.append(message)

            elif message_type == "ob_updates":
                updates.append(message)

    trades.sort(key=lambda x: x["t"])
    updates.sort(key=lambda x: x["ts"])

    return trades, updates


def reconstruct_books(updates):
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

        if not asks or not bids:
            continue

        best_ask = min(
            float(price)
            for price in asks
        )

        best_bid = max(
            float(price)
            for price in bids
        )

        timeline.append({
            "ts": int(message["ts"]),
            "seq": int(message["seq"]),
            "best_bid": best_bid,
            "best_ask": best_ask,
            "mid_price": (
                best_bid + best_ask
            ) / 2.0,
        })

    return timeline


def main():

    trades, updates = load_records()

    books = reconstruct_books(updates)

    book_times = [
        row["ts"]
        for row in books
    ]

    synchronized = 0
    future_quotes = 0
    unknown = 0

    ages = []

    with OUTPUT.open("w") as out:

        for trade in trades:

            trade_time = int(trade["t"])

            index = bisect.bisect_right(
                book_times,
                trade_time
            ) - 1

            if index < 0:

                unknown += 1

                result = {
                    "trade_ts": trade_time,
                    "trade_feed_ts": trade.get("ts"),
                    "trade_price": trade.get("p"),
                    "trade_size": trade.get("s"),
                    "role": trade.get("r"),
                    "book_ts": None,
                    "book_seq": None,
                    "book_age_us": None,
                    "best_bid": None,
                    "best_ask": None,
                    "mid_price": None,
                }

            else:

                book = books[index]

                age = (
                    trade_time
                    - book["ts"]
                )

                if age < 0:
                    future_quotes += 1

                ages.append(age)

                synchronized += 1

                result = {
                    "trade_ts": trade_time,
                    "trade_feed_ts": trade.get("ts"),
                    "trade_price": trade.get("p"),
                    "trade_size": trade.get("s"),
                    "role": trade.get("r"),
                    "book_ts": book["ts"],
                    "book_seq": book["seq"],
                    "book_age_us": age,
                    "best_bid": book["best_bid"],
                    "best_ask": book["best_ask"],
                    "mid_price": book["mid_price"],
                }

            out.write(
                json.dumps(result)
                + "\n"
            )

    print("=" * 72)
    print("LARGE SESSION SYNCHRONIZATION V1")
    print("=" * 72)

    print(f"trades             : {len(trades)}")
    print(f"book states        : {len(books)}")
    print(f"synchronized       : {synchronized}")
    print(f"unknown             : {unknown}")
    print(f"future quote count : {future_quotes}")

    if ages:

        ages_sorted = sorted(ages)

        def percentile(p):
            index = int(
                (len(ages_sorted) - 1) * p
            )

            return ages_sorted[index]

        print()
        print("BOOK AGE (microseconds)")
        print(f"min                : {min(ages)}")
        print(f"p50                : {percentile(0.50)}")
        print(f"p90                : {percentile(0.90)}")
        print(f"p95                : {percentile(0.95)}")
        print(f"p99                : {percentile(0.99)}")
        print(f"max                : {max(ages)}")
        print(
            f"mean               : "
            f"{sum(ages) / len(ages):.1f}"
        )

    print()
    print(f"OUTPUT             : {OUTPUT}")


if __name__ == "__main__":
    main()
