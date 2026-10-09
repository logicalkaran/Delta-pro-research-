import csv
from collections import defaultdict
from pathlib import Path


INPUT_FILE = "data/processed/btc_trade_flow_v1.csv"
OUTPUT_FILE = "data/processed/btc_trade_flow_features_v2.csv"

BUCKET_US = 1_000_000


def bucket_timestamp(timestamp):
    return (int(timestamp) // BUCKET_US) * BUCKET_US


def main():

    buckets = defaultdict(
        lambda: {
            "buy_volume": 0.0,
            "sell_volume": 0.0,
            "unknown_volume": 0.0,
            "buy_trades": 0,
            "sell_trades": 0,
            "unknown_trades": 0,
            "total_trades": 0,
            "total_volume": 0.0,
            "max_trade_size": 0.0,
            "price_first": None,
            "price_last": None,
        }
    )

    with open(INPUT_FILE, encoding="utf-8") as f:

        reader = csv.DictReader(f)

        for row in reader:

            timestamp = int(row["trade_timestamp"])
            price = float(row["price"])
            size = float(row["size"])
            side = row["side"]

            bucket = bucket_timestamp(timestamp)

            data = buckets[bucket]

            if data["price_first"] is None:
                data["price_first"] = price

            data["price_last"] = price

            data["total_trades"] += 1
            data["total_volume"] += size

            if size > data["max_trade_size"]:
                data["max_trade_size"] = size

            if side == "buy":

                data["buy_volume"] += size
                data["buy_trades"] += 1

            elif side == "sell":

                data["sell_volume"] += size
                data["sell_trades"] += 1

            else:

                data["unknown_volume"] += size
                data["unknown_trades"] += 1

    rows = []

    cumulative_delta = 0.0

    for timestamp in sorted(buckets):

        data = buckets[timestamp]

        net_delta = (
            data["buy_volume"]
            - data["sell_volume"]
        )

        cumulative_delta += net_delta

        known_volume = (
            data["buy_volume"]
            + data["sell_volume"]
        )

        if known_volume > 0:
            delta_ratio = net_delta / known_volume
        else:
            delta_ratio = 0.0

        rows.append({
            "timestamp": timestamp,
            "price_first": data["price_first"],
            "price_last": data["price_last"],
            "total_trades": data["total_trades"],
            "total_volume": data["total_volume"],
            "buy_trades": data["buy_trades"],
            "sell_trades": data["sell_trades"],
            "unknown_trades": data["unknown_trades"],
            "buy_volume": data["buy_volume"],
            "sell_volume": data["sell_volume"],
            "unknown_volume": data["unknown_volume"],
            "net_delta": net_delta,
            "delta_ratio": delta_ratio,
            "cumulative_delta": cumulative_delta,
            "max_trade_size": data["max_trade_size"],
        })

    if not rows:
        raise RuntimeError("No trade-flow buckets generated")

    output = Path(OUTPUT_FILE)
    output.parent.mkdir(parents=True, exist_ok=True)

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
    print("TRADE FLOW FEATURES V2")
    print("=" * 60)

    print(f"input       : {INPUT_FILE}")
    print(f"output      : {OUTPUT_FILE}")
    print(f"buckets     : {len(rows)}")

    total_buy = sum(r["buy_volume"] for r in rows)
    total_sell = sum(r["sell_volume"] for r in rows)

    print()
    print("TOTAL FLOW")
    print("-" * 60)
    print(f"buy volume  : {total_buy}")
    print(f"sell volume : {total_sell}")
    print(f"net delta   : {total_buy - total_sell}")

    print()
    print("LAST 5 BUCKETS")
    print("-" * 60)

    for row in rows[-5:]:
        print(row)


if __name__ == "__main__":
    main()
