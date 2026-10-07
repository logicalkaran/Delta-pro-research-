import csv
from collections import Counter


INPUT_FILE = "data/processed/btc_trade_flow_v1.csv"


def main():

    rows = []

    with open(INPUT_FILE, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    role_counts = Counter(row["role"] for row in rows)
    side_counts = Counter(row["side"] for row in rows)

    volume_by_side = Counter()
    volume_by_role = Counter()

    for row in rows:
        size = float(row["size"])

        volume_by_side[row["side"]] += size
        volume_by_role[row["role"]] += size

    print("=" * 60)
    print("TRADE FLOW DIAGNOSTICS V1")
    print("=" * 60)

    print()
    print("TRADE COUNT BY ROLE")
    print("-" * 60)

    for key, value in role_counts.items():
        print(f"{key:12}: {value}")

    print()
    print("TRADE COUNT BY ESTIMATED SIDE")
    print("-" * 60)

    for key, value in side_counts.items():
        print(f"{key:12}: {value}")

    print()
    print("VOLUME BY ESTIMATED SIDE")
    print("-" * 60)

    for key, value in volume_by_side.items():
        print(f"{key:12}: {value}")

    print()
    print("VOLUME BY ROLE")
    print("-" * 60)

    for key, value in volume_by_role.items():
        print(f"{key:12}: {value}")

    known_volume = (
        volume_by_side["buy"]
        + volume_by_side["sell"]
    )

    if known_volume:
        print()
        print(
            "KNOWN-SIDE BUY VOLUME RATIO : "
            f"{volume_by_side['buy'] / known_volume:.2%}"
        )

    print()
    print("NOTE")
    print("-" * 60)
    print(
        "role is preserved as exchange metadata. "
        "It is NOT interpreted as buy/sell direction."
    )


if __name__ == "__main__":
    main()
