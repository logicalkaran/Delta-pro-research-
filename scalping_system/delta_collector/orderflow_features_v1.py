import csv
import json
from pathlib import Path

from .orderbook_v2 import DeltaOrderBook


RAW_FILE = "data/raw/delta_btc_ob_updates.jsonl"
OUTPUT_FILE = "data/processed/btc_orderflow_features_v1.csv"


def depth(book, side, levels):
    if side == "bid":
        prices = sorted(
            book.bids.keys(),
            key=float,
            reverse=True,
        )[:levels]
        return sum(book.bids[p] for p in prices)

    prices = sorted(
        book.asks.keys(),
        key=float,
    )[:levels]

    return sum(book.asks[p] for p in prices)


def imbalance(bid_depth, ask_depth):
    total = bid_depth + ask_depth

    if total == 0:
        return 0.0

    return (bid_depth - ask_depth) / total


def build_features(book, message):
    bid = book.best_bid()
    ask = book.best_ask()

    if bid is None or ask is None:
        return None

    bid_depth_5 = depth(book, "bid", 5)
    ask_depth_5 = depth(book, "ask", 5)

    bid_depth_10 = depth(book, "bid", 10)
    ask_depth_10 = depth(book, "ask", 10)

    bid_float = float(bid)
    ask_float = float(ask)

    mid = (bid_float + ask_float) / 2.0

    return {
        "seq": book.last_seq,
        "timestamp": message.get("ts"),
        "best_bid": bid_float,
        "best_ask": ask_float,
        "mid_price": mid,
        "spread": ask_float - bid_float,

        "bid_depth_5": bid_depth_5,
        "ask_depth_5": ask_depth_5,
        "imbalance_5": imbalance(
            bid_depth_5,
            ask_depth_5,
        ),

        "bid_depth_10": bid_depth_10,
        "ask_depth_10": ask_depth_10,
        "imbalance_10": imbalance(
            bid_depth_10,
            ask_depth_10,
        ),
    }


def main():
    book = DeltaOrderBook()

    output = Path(OUTPUT_FILE)
    output.parent.mkdir(parents=True, exist_ok=True)

    rows = []

    with open(RAW_FILE, encoding="utf-8") as f:

        for line in f:

            record = json.loads(line)
            message = record["message"]

            if message.get("type") != "ob_updates":
                continue

            action = message.get("action")

            if action == "snapshot":

                book.load_snapshot(message)

                row = build_features(book, message)

                if row:
                    rows.append(row)

            elif action == "update":

                book.apply_update(message)

                row = build_features(book, message)

                if row:
                    rows.append(row)

    if not rows:
        raise RuntimeError("No order-flow features generated")

    fieldnames = list(rows[0].keys())

    with output.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
        )

        writer.writeheader()
        writer.writerows(rows)

    print("=" * 60)
    print("ORDER-FLOW FEATURE ENGINE V1")
    print("=" * 60)

    print(f"input       : {RAW_FILE}")
    print(f"output      : {OUTPUT_FILE}")
    print(f"rows        : {len(rows)}")

    print()
    print("LAST FEATURE ROW")
    print("-" * 60)

    for key, value in rows[-1].items():
        print(f"{key:16}: {value}")


if __name__ == "__main__":
    main()
