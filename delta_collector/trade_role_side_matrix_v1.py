import csv
from collections import defaultdict


INPUT_FILE = "data/processed/btc_trade_flow_v1.csv"


def main():

    counts = defaultdict(int)
    volumes = defaultdict(float)

    with open(INPUT_FILE, encoding="utf-8") as f:

        reader = csv.DictReader(f)

        for row in reader:

            role = row["role"]
            side = row["side"]
            size = float(row["size"])

            counts[(role, side)] += 1
            volumes[(role, side)] += size

    print("=" * 60)
    print("TRADE ROLE / ESTIMATED SIDE MATRIX")
    print("=" * 60)

    roles = ["t", "m"]
    sides = ["buy", "sell", "unknown"]

    print()
    print("TRADE COUNT")
    print("-" * 60)

    print(f"{'role':10}{'buy':>12}{'sell':>12}{'unknown':>12}")

    for role in roles:

        print(
            f"{role:10}"
            f"{counts[(role, 'buy')]:>12}"
            f"{counts[(role, 'sell')]:>12}"
            f"{counts[(role, 'unknown')]:>12}"
        )

    print()
    print("TRADED VOLUME")
    print("-" * 60)

    print(f"{'role':10}{'buy':>12}{'sell':>12}{'unknown':>12}")

    for role in roles:

        print(
            f"{role:10}"
            f"{volumes[(role, 'buy')]:>12.1f}"
            f"{volumes[(role, 'sell')]:>12.1f}"
            f"{volumes[(role, 'unknown')]:>12.1f}"
        )

    print()
    print("INTERPRETATION")
    print("-" * 60)
    print(
        "This matrix is descriptive only. "
        "It does not define maker/taker as buy/sell."
    )


if __name__ == "__main__":
    main()
