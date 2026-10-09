import json
import statistics
from pathlib import Path


INPUT = Path(
    "data/processed/btc_microstructure_features_v1.jsonl"
)

HORIZONS = [1, 5, 10, 30]

AGE_LIMITS = [
    ("20ms", 20_000),
    ("50ms", 50_000),
    ("100ms", 100_000),
    ("200ms", 200_000),
]

BUCKETS = [
    ("strong_negative", float("-inf"), -0.60),
    ("negative", -0.60, -0.20),
    ("neutral", -0.20, 0.20),
    ("positive", 0.20, 0.60),
    ("strong_positive", 0.60, float("inf")),
]


def load_rows():
    rows = []

    with INPUT.open() as f:
        for line in f:
            line = line.strip()

            if not line:
                continue

            row = json.loads(line)

            # Require the fields needed for time-series research.
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
    current_time = rows[index]["trade_ts"]

    target = current_time + horizon_seconds * 1_000_000

    current_price = float(rows[index]["trade_price"])

    if current_price <= 0:
        return None

    for j in range(index + 1, len(rows)):
        future_time = rows[j]["trade_ts"]

        if future_time >= target:
            future_price = float(rows[j]["trade_price"])

            if future_price <= 0:
                return None

            return (future_price / current_price) - 1.0

    return None


def analyze(rows, age_limit):
    results = {}

    for horizon in HORIZONS:
        buckets = {
            name: []
            for name, _, _ in BUCKETS
        }

        for i, row in enumerate(rows):

            age = row.get("book_age_us")
            imbalance = row.get("imbalance_5")

            # Require valid synchronized book data.
            if age is None:
                continue

            if imbalance is None:
                continue

            try:
                age = float(age)
                imbalance = float(imbalance)
            except (TypeError, ValueError):
                continue

            if age > age_limit:
                continue

            bucket = get_bucket(imbalance)

            if bucket is None:
                continue

            ret = forward_return(rows, i, horizon)

            if ret is None:
                continue

            buckets[bucket].append(ret)

        results[horizon] = buckets

    return results


def main():
    rows = load_rows()

    print("=" * 75)
    print("IMBALANCE × FRESHNESS RESEARCH V2")
    print("=" * 75)

    print(f"INPUT ROWS: {len(rows)}")

    for age_name, age_limit in AGE_LIMITS:

        print()
        print("=" * 75)
        print(f"BOOK AGE <= {age_name}")
        print("=" * 75)

        results = analyze(rows, age_limit)

        for horizon in HORIZONS:

            print()
            print(f"HORIZON {horizon}s")
            print("-" * 75)

            for bucket_name, _, _ in BUCKETS:

                values = results[horizon][bucket_name]

                if not values:
                    print(
                        f"{bucket_name:<18} "
                        f"N=  0 mean=N/A"
                    )
                    continue

                mean_return = statistics.mean(values)

                print(
                    f"{bucket_name:<18} "
                    f"N={len(values):3d} "
                    f"mean={mean_return:+.8f}"
                )


if __name__ == "__main__":
    main()
