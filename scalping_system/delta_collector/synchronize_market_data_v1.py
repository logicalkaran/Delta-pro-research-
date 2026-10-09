import csv
import json
from pathlib import Path


INPUT_FILE = "data/raw/delta_btc_session_v1.jsonl"
OUTPUT_FILE = "data/processed/btc_synchronized_trades_v1.csv"


def classify_trade(price, bid, ask):
    if bid is None or ask is None:
        return "unknown"

    if price >= ask:
        return "buy"

    if price <= bid:
        return "sell"

    return "unknown"


def main():

    latest_bid = None
    latest_ask = None
    latest_l1_ts = None

    trades = 0
    buy = 0
    sell = 0
    unknown = 0

    rows = []

    with open(INPUT_FILE, encoding="utf-8") as f:

        for line in f:

            record = json.loads(line)
            message = record["message"]

            msg_type = message.get("type")

            if msg_type == "ob_l1":

                try:
                    latest_bid = float(message["bp"])
                    latest_ask = float(message["ap"])
                    latest_l1_ts = int(message["ts"])
                except (
                    KeyError,
                    TypeError,
                    ValueError,
                ):
                    continue

            elif msg_type == "trades":

                try:
                    trade_ts = int(message["t"])
                    feed_ts = int(message["ts"])
                    price = float(message["p"])
                    size = float(message["s"])
                except (
                    KeyError,
                    TypeError,
                    ValueError,
                ):
                    continue

                trades += 1

                if latest_l1_ts is None:
                    side = "unknown"
                    book_age_us = None
                else:
                    book_age_us = trade_ts - latest_l1_ts

                    side = classify_trade(
                        price,
                        latest_bid,
                        latest_ask,
                    )

                if side == "buy":
                    buy += 1
                elif side == "sell":
                    sell += 1
                else:
                    unknown += 1

                rows.append({
                    "trade_ts": trade_ts,
                    "feed_ts": feed_ts,
                    "price": price,
                    "size": size,
                    "role": message.get("r"),

                    "best_bid": latest_bid,
                    "best_ask": latest_ask,

                    "book_ts": latest_l1_ts,
                    "book_age_us": book_age_us,

                    "side": side,
                })

    if not rows:
        raise RuntimeError(
            "No synchronized trades generated"
        )

    output = Path(OUTPUT_FILE)
    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

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
    print("SYNCHRONIZED MARKET DATA V1")
    print("=" * 60)

    print(f"input       : {INPUT_FILE}")
    print(f"output      : {OUTPUT_FILE}")

    print()
    print("TRADE COUNTS")
    print("-" * 60)

    print(f"trades      : {trades}")
    print(f"buy         : {buy}")
    print(f"sell        : {sell}")
    print(f"unknown     : {unknown}")

    known = buy + sell

    if trades:
        print(
            f"known ratio : "
            f"{known / trades:.2%}"
        )

    valid_ages = [
        row["book_age_us"]
        for row in rows
        if row["book_age_us"] is not None
    ]

    if valid_ages:

        print()
        print("BOOK AGE")
        print("-" * 60)

        print(
            f"min us      : {min(valid_ages)}"
        )

        print(
            f"max us      : {max(valid_ages)}"
        )

        print(
            f"avg us      : "
            f"{sum(valid_ages) / len(valid_ages):.1f}"
        )

    print()
    print("SAMPLE")
    print("-" * 60)

    for row in rows[:10]:
        print(row)


if __name__ == "__main__":
    main()
