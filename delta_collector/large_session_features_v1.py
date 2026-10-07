import json
import sys
from pathlib import Path


if len(sys.argv) != 2:
    print(
        "Usage:\n"
        "python -m delta_collector.large_session_features_v1 "
        "<synchronized_file>"
    )
    raise SystemExit(1)


INPUT = Path(sys.argv[1])

OUTPUT = INPUT.with_name(
    INPUT.stem + "_features.jsonl"
)


def main():

    cumulative_delta = 0.0
    rows = 0

    quality_counts = {
        "high": 0,
        "medium": 0,
        "low": 0,
        "stale": 0,
        "unknown": 0,
    }

    with INPUT.open() as src, OUTPUT.open("w") as dst:

        for line in src:

            line = line.strip()

            if not line:
                continue

            row = json.loads(line)

            rows += 1

            age = row.get("book_age_us")

            bid = row.get("best_bid")
            ask = row.get("best_ask")

            price = row.get("trade_price")
            size = row.get("trade_size")

            if age is None:
                quality = "unknown"

            elif age <= 20_000:
                quality = "high"

            elif age <= 50_000:
                quality = "medium"

            elif age <= 100_000:
                quality = "low"

            else:
                quality = "stale"

            quality_counts[quality] += 1

            if (
                price is None
                or size is None
                or bid is None
                or ask is None
            ):
                trade_delta = 0.0
                estimated_side = "unknown"

            else:

                price = float(price)
                size = float(size)
                bid = float(bid)
                ask = float(ask)

                if price >= ask:
                    estimated_side = "buy"
                    trade_delta = size

                elif price <= bid:
                    estimated_side = "sell"
                    trade_delta = -size

                else:
                    estimated_side = "unknown"
                    trade_delta = 0.0

            cumulative_delta += trade_delta

            if bid is not None and ask is not None:

                bid = float(bid)
                ask = float(ask)

                mid = (bid + ask) / 2.0
                spread = ask - bid

            else:

                mid = None
                spread = None

            result = {
                **row,
                "estimated_side": estimated_side,
                "trade_delta": trade_delta,
                "cumulative_delta": cumulative_delta,
                "quality": quality,
                "mid_price_valid": mid is not None,
                "spread_valid": spread is not None,
            }

            dst.write(
                json.dumps(result)
                + "\n"
            )

    print("=" * 72)
    print("LARGE SESSION FEATURE GENERATION V1")
    print("=" * 72)

    print(f"rows written : {rows}")

    print()
    print("QUALITY")

    for key in quality_counts:
        print(
            f"{key:<10}: "
            f"{quality_counts[key]}"
        )

    print()
    print(
        f"final CVD   : "
        f"{cumulative_delta}"
    )

    print()
    print(f"OUTPUT      : {OUTPUT}")


if __name__ == "__main__":
    main()
