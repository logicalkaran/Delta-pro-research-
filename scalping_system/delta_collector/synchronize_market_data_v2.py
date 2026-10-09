import bisect
import csv
import json
from pathlib import Path


INPUT_FILE = "data/raw/delta_btc_session_v1.jsonl"
OUTPUT_FILE = "data/processed/btc_synchronized_trades_v2.csv"


def classify_trade(price, bid, ask):
    if bid is None or ask is None:
        return "unknown"

    if price >= ask:
        return "buy"

    if price <= bid:
        return "sell"

    return "unknown"


def main():

    events = []
    l1_states = []
    trades = []

    with open(INPUT_FILE, encoding="utf-8") as f:

        for line_number, line in enumerate(f, 1):

            record = json.loads(line)
            message = record["message"]

            msg_type = message.get("type")

            if msg_type == "ob_l1":

                try:
                    ts = int(message["ts"])
                    bid = float(message["bp"])
                    ask = float(message["ap"])
                except (
                    KeyError,
                    TypeError,
                    ValueError,
                ):
                    continue

                l1_states.append({
                    "ts": ts,
                    "bid": bid,
                    "ask": ask,
                    "line": line_number,
                })

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

                trades.append({
                    "trade_ts": trade_ts,
                    "feed_ts": feed_ts,
                    "price": price,
                    "size": size,
                    "role": message.get("r"),
                    "line": line_number,
                })

    if not l1_states:
        raise RuntimeError("No L1 states found")

    if not trades:
        raise RuntimeError("No trades found")

    # Sort by exchange timestamp.
    l1_states.sort(key=lambda x: x["ts"])
    trades.sort(key=lambda x: x["trade_ts"])

    l1_times = [
        state["ts"]
        for state in l1_states
    ]

    rows = []

    buy = 0
    sell = 0
    unknown = 0

    future_quote_count = 0

    for trade in trades:

        trade_ts = trade["trade_ts"]

        # Find the newest L1 state whose exchange timestamp
        # is <= the trade timestamp.
        index = bisect.bisect_right(
            l1_times,
            trade_ts,
        ) - 1

        if index < 0:

            bid = None
            ask = None
            book_ts = None
            book_age_us = None

        else:

            state = l1_states[index]

            bid = state["bid"]
            ask = state["ask"]
            book_ts = state["ts"]

            book_age_us = trade_ts - book_ts

            if book_age_us < 0:
                future_quote_count += 1

        side = classify_trade(
            trade["price"],
            bid,
            ask,
        )

        if side == "buy":
            buy += 1
        elif side == "sell":
            sell += 1
        else:
            unknown += 1

        rows.append({
            "trade_ts": trade_ts,
            "feed_ts": trade["feed_ts"],
            "price": trade["price"],
            "size": trade["size"],
            "role": trade["role"],

            "best_bid": bid,
            "best_ask": ask,

            "book_ts": book_ts,
            "book_age_us": book_age_us,

            "side": side,
        })

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

    valid_ages = [
        row["book_age_us"]
        for row in rows
        if row["book_age_us"] is not None
    ]

    print("=" * 60)
    print("SYNCHRONIZED MARKET DATA V2")
    print("=" * 60)

    print(f"input              : {INPUT_FILE}")
    print(f"output             : {OUTPUT_FILE}")

    print()
    print("EVENT COUNTS")
    print("-" * 60)

    print(f"L1 states          : {len(l1_states)}")
    print(f"trades             : {len(trades)}")
    print(f"buy                : {buy}")
    print(f"sell               : {sell}")
    print(f"unknown            : {unknown}")

    print()
    print("BOOK AGE")
    print("-" * 60)

    if valid_ages:

        print(
            f"min us             : "
            f"{min(valid_ages)}"
        )

        print(
            f"max us             : "
            f"{max(valid_ages)}"
        )

        print(
            f"avg us             : "
            f"{sum(valid_ages) / len(valid_ages):.1f}"
        )

    print()
    print(
        f"future quote count : "
        f"{future_quote_count}"
    )

    print()
    print("SAMPLE")
    print("-" * 60)

    for row in rows[:10]:
        print(row)


if __name__ == "__main__":
    main()
