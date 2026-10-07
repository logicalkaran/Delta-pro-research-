import json
from collections import Counter

INPUT_FILE = "data/processed/btc_research_synchronized_v1.jsonl"


def classify_age(age):
    if age is None:
        return "unknown"

    if age <= 20_000:
        return "high"

    if age <= 50_000:
        return "medium"

    if age <= 100_000:
        return "low"

    return "stale"


def main():
    rows = []

    with open(INPUT_FILE, "r") as f:
        for line in f:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    quality_counts = Counter()
    side_counts = Counter()

    volume_by_quality = Counter()
    trades_by_quality = Counter()

    age_values = []

    for row in rows:
        age = row.get("book_age_us")
        quality = classify_age(age)

        quality_counts[quality] += 1
        trades_by_quality[quality] += 1

        if age is not None:
            age_values.append(age)

        side = row.get("estimated_side", "unknown")
        side_counts[side] += 1

        size = row.get("trade_size")

        if size is not None:
            try:
                volume_by_quality[quality] += float(size)
            except (TypeError, ValueError):
                pass

    print("=" * 60)
    print("SYNCHRONIZATION QUALITY V2")
    print("=" * 60)

    print()
    print("TRADE COUNT")
    print("-" * 60)

    for quality in ("high", "medium", "low", "stale", "unknown"):
        print(
            f"{quality:12} : "
            f"{trades_by_quality[quality]}"
        )

    print()
    print("TRADED VOLUME")
    print("-" * 60)

    for quality in ("high", "medium", "low", "stale", "unknown"):
        print(
            f"{quality:12} : "
            f"{volume_by_quality[quality]}"
        )

    print()
    print("ESTIMATED SIDE")
    print("-" * 60)

    for side in ("buy", "sell", "unknown"):
        print(
            f"{side:12} : "
            f"{side_counts[side]}"
        )

    if age_values:
        print()
        print("AGE DISTRIBUTION")
        print("-" * 60)

        sorted_ages = sorted(age_values)

        def percentile(values, p):
            index = int((len(values) - 1) * p)
            return values[index]

        print(
            f"p50 age us  : "
            f"{percentile(sorted_ages, 0.50)}"
        )

        print(
            f"p90 age us  : "
            f"{percentile(sorted_ages, 0.90)}"
        )

        print(
            f"p95 age us  : "
            f"{percentile(sorted_ages, 0.95)}"
        )

        print(
            f"p99 age us  : "
            f"{percentile(sorted_ages, 0.99)}"
        )

        print(
            f"max age us  : "
            f"{max(sorted_ages)}"
        )


if __name__ == "__main__":
    main()
