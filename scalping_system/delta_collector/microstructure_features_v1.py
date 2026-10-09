import json
from collections import defaultdict

INPUT_FILE = "data/processed/btc_research_synchronized_v1.jsonl"
OUTPUT_FILE = "data/processed/btc_microstructure_features_v1.jsonl"


def quality(age):
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

    cumulative_delta = 0.0

    output = []

    for row in rows:
        age = row.get("book_age_us")
        q = quality(age)

        side = row.get("estimated_side")
        size = row.get("trade_size")

        try:
            size = float(size)
        except (TypeError, ValueError):
            size = 0.0

        if side == "buy":
            trade_delta = size
        elif side == "sell":
            trade_delta = -size
        else:
            trade_delta = 0.0

        cumulative_delta += trade_delta

        bid = row.get("best_bid")
        ask = row.get("best_ask")

        mid = row.get("mid_price")
        spread = row.get("spread")

        output_row = dict(row)

        output_row.update({
            "quality": q,
            "trade_delta": trade_delta,
            "cumulative_delta": cumulative_delta,
            "valid_side": side in ("buy", "sell"),
            "book_valid": (
                bid is not None
                and ask is not None
            ),
            "mid_price_valid": mid is not None,
            "spread_valid": spread is not None,
        })

        output.append(output_row)

    with open(OUTPUT_FILE, "w") as f:
        for row in output:
            f.write(json.dumps(row) + "\n")

    counts = defaultdict(int)
    volume = defaultdict(float)

    for row in output:
        q = row["quality"]
        counts[q] += 1

        try:
            volume[q] += float(row["trade_size"])
        except (TypeError, ValueError):
            pass

    print("=" * 60)
    print("MICROSTRUCTURE FEATURES V1")
    print("=" * 60)

    print()
    print("OBSERVATIONS")
    print("-" * 60)

    for q in ("high", "medium", "low", "stale", "unknown"):
        print(f"{q:12} : {counts[q]}")

    print()
    print("TRADED VOLUME")
    print("-" * 60)

    for q in ("high", "medium", "low", "stale", "unknown"):
        print(f"{q:12} : {volume[q]}")

    print()
    print(f"rows written      : {len(output)}")
    print(f"final CVD         : {cumulative_delta}")
    print(f"output            : {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
