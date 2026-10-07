import csv
import json
from pathlib import Path


RAW_FILE = "data/raw/delta_btc_raw.jsonl"
OUTPUT_FILE = "data/processed/btc_trade_flow_v1.csv"


def classify_trade(price, bid, ask):
    """
    Conservative aggressor-side classification.

    BUY:
        trade executes at/above best ask

    SELL:
        trade executes at/below best bid

    UNKNOWN:
        trade falls between bid and ask or book is unavailable.
    """

    if bid is None or ask is None:
        return "unknown"

    if price >= ask:
        return "buy"

    if price <= bid:
        return "sell"

    return "unknown"


def main():

    events = []
    best_bid = None
    best_ask = None

    trades = 0
    classified_buy = 0
    classified_sell = 0
    classified_unknown = 0

    with open(RAW_FILE, encoding="utf-8") as f:

        for line in f:

            record = json.loads(line)
            message = record["message"]

            msg_type = message.get("type")

            if msg_type == "ob_l1":

                try:
                    best_ask = float(message["ap"])
                    best_bid = float(message["bp"])
                except (KeyError, TypeError, ValueError):
                    continue

            elif msg_type == "trades":

                try:
                    price = float(message["p"])
                    size = float(message["s"])
                except (KeyError, TypeError, ValueError):
                    continue

                side = classify_trade(
                    price,
                    best_bid,
                    best_ask,
                )

                trades += 1

                if side == "buy":
                    classified_buy += 1
                elif side == "sell":
                    classified_sell += 1
                else:
                    classified_unknown += 1

                events.append({
                    "received_at": record.get("received_at"),
                    "trade_timestamp": message.get("t"),
                    "feed_timestamp": message.get("ts"),
                    "price": price,
                    "size": size,
                    "role": message.get("r"),
                    "best_bid": best_bid,
                    "best_ask": best_ask,
                    "side": side,
                })

    if not events:
        raise RuntimeError("No trades found")

    output = Path(OUTPUT_FILE)
    output.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = list(events[0].keys())

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
        writer.writerows(events)

    print("=" * 60)
    print("TRADE FLOW V1")
    print("=" * 60)

    print(f"input             : {RAW_FILE}")
    print(f"output            : {OUTPUT_FILE}")
    print(f"trades            : {trades}")
    print(f"classified buy    : {classified_buy}")
    print(f"classified sell   : {classified_sell}")
    print(f"classified unknown : {classified_unknown}")

    print()

    if trades:
        print(
            f"known-side ratio  : "
            f"{(classified_buy + classified_sell) / trades:.2%}"
        )

    print()
    print("LAST 5 TRADES")
    print("-" * 60)

    for row in events[-5:]:
        print(row)


if __name__ == "__main__":
    main()
