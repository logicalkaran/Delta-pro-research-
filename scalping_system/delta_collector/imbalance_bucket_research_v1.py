import json
import bisect
import statistics

INPUT_FILE = "data/processed/btc_microstructure_features_v1.jsonl"

HORIZONS_US = {
    "1s": 1_000_000,
    "5s": 5_000_000,
    "10s": 10_000_000,
    "30s": 30_000_000,
}


def safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def bucket(value):
    if value is None:
        return "unknown"

    if value <= -0.60:
        return "strong_negative"

    if value <= -0.20:
        return "negative"

    if value < 0.20:
        return "neutral"

    if value < 0.60:
        return "positive"

    return "strong_positive"


def main():
    rows = []

    with open(INPUT_FILE, "r") as f:
        for line in f:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    rows.sort(
        key=lambda x: int(x.get("trade_ts", 0))
    )

    timestamps = [
        int(row["trade_ts"])
        for row in rows
    ]

    prices = [
        safe_float(row.get("trade_price"))
        for row in rows
    ]

    print("=" * 75)
    print("IMBALANCE BUCKET RESEARCH V1")
    print("=" * 75)

    for horizon_name, horizon_us in HORIZONS_US.items():

        buckets = {}

        for i, row in enumerate(rows):

            current_price = prices[i]

            if current_price is None or current_price == 0:
                continue

            target_ts = timestamps[i] + horizon_us

            j = bisect.bisect_left(
                timestamps,
                target_ts,
                lo=i + 1
            )

            if j >= len(rows):
                continue

            future_price = prices[j]

            if future_price is None:
                continue

            imbalance = safe_float(
                row.get("imbalance_5")
            )

            b = bucket(imbalance)

            if b == "unknown":
                continue

            forward_return = (
                future_price / current_price
                - 1.0
            )

            buckets.setdefault(b, []).append(
                forward_return
            )

        print()
        print(f"HORIZON {horizon_name}")
        print("-" * 75)

        order = [
            "strong_negative",
            "negative",
            "neutral",
            "positive",
            "strong_positive",
        ]

        for b in order:
            values = buckets.get(b, [])

            if not values:
                print(f"{b:18} N=0")
                continue

            print(
                f"{b:18} "
                f"N={len(values):3d} "
                f"mean={statistics.mean(values): .8f}"
            )


if __name__ == "__main__":
    main()
