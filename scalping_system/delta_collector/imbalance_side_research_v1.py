import json
import statistics
from pathlib import Path


INPUT = Path(
    "data/processed/btc_microstructure_features_v1.jsonl"
)

HORIZONS = [1, 5, 10, 30]

MAX_AGE_US = 100_000

BUCKETS = [
    ("strong_negative", float("-inf"), -0.60),
    ("negative", -0.60, -0.20),
    ("neutral", -0.20, 0.20),
    ("positive", 0.20, 0.60),
    ("strong_positive", 0.60, float("inf")),
]

SIDES = ["buy", "sell"]


def load_rows():
    rows = []

    with INPUT.open() as f:
        for line in f:
            line = line.strip()

            if not line:
                continue

            row = json.loads(line)

            if row.get("trade_ts") is None:
                continue

            if row.get("trade_price") is None:
                continue

            rows.append(row)

    rows.sort(key=lambda x: x["trade_ts"])

    return rows


def get_bucket(value):
    for name, low, high in BUCKETS:
        if low <= value < high:
            return name

    return None


def forward_return(rows, index, horizon_seconds):
    current_ts = rows[index]["trade_ts"]
    target_ts = current_ts + horizon_seconds * 1_000_000

    current_price = float(rows[index]["trade_price"])

    if current_price <= 0:
        return None

    for j in range(index + 1, len(rows)):
        if rows[j]["trade_ts"] >= target_ts:
            future_price = float(rows[j]["trade_price"])

            if future_price <= 0:
                return None

            return (future_price / current_price) - 1.0

    return None


def main():
    rows = load_rows()

    print("=" * 78)
    print("IMBALANCE × ESTIMATED SIDE RESEARCH V1")
    print("=" * 78)

    print(f"INPUT ROWS       : {len(rows)}")
    print(f"MAX BOOK AGE     : {MAX_AGE_US / 1000:.0f} ms")

    for horizon in HORIZONS:

        print()
        print("=" * 78)
        print(f"HORIZON {horizon}s")
        print("=" * 78)

        results = {
            side: {
                bucket: []
                for bucket, _, _ in BUCKETS
            }
            for side in SIDES
        }

        for i, row in enumerate(rows):

            age = row.get("book_age_us")
            imbalance = row.get("imbalance_5")
            side = row.get("estimated_side")

            if age is None or imbalance is None:
                continue

            if side not in SIDES:
                continue

            try:
                age = float(age)
                imbalance = float(imbalance)
            except (TypeError, ValueError):
                continue

            if age > MAX_AGE_US:
                continue

            bucket = get_bucket(imbalance)

            if bucket is None:
                continue

            ret = forward_return(rows, i, horizon)

            if ret is None:
                continue

            results[side][bucket].append(ret)

        for side in SIDES:

            print()
            print(f"{side.upper()}")
            print("-" * 78)

            for bucket, _, _ in BUCKETS:

                values = results[side][bucket]

                if not values:
                    print(
                        f"{bucket:<18} "
                        f"N=  0 mean=N/A"
                    )
                    continue

                mean_return = statistics.mean(values)

                print(
                    f"{bucket:<18} "
                    f"N={len(values):3d} "
                    f"mean={mean_return:+.8f}"
                )


if __name__ == "__main__":
    main()
