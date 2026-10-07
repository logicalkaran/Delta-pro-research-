import csv
from collections import Counter


INPUT_FILE = "data/processed/btc_synchronized_trades_v2.csv"


def quality(book_age_us):

    if book_age_us is None:
        return "unknown"

    age = float(book_age_us)

    if age <= 20_000:
        return "high"

    if age <= 50_000:
        return "medium"

    return "low"


def main():

    counts = Counter()
    volumes = Counter()

    total = 0

    with open(INPUT_FILE, encoding="utf-8") as f:

        reader = csv.DictReader(f)

        for row in reader:

            total += 1

            age = row["book_age_us"]

            if age == "":
                q = "unknown"
            else:
                q = quality(float(age))

            size = float(row["size"])

            counts[q] += 1
            volumes[q] += size

    print("=" * 60)
    print("SYNCHRONIZATION QUALITY V1")
    print("=" * 60)

    print()
    print("TRADE COUNT")
    print("-" * 60)

    for key in [
        "high",
        "medium",
        "low",
        "unknown",
    ]:
        print(
            f"{key:10}: {counts[key]}"
        )

    print()
    print("TRADED VOLUME")
    print("-" * 60)

    for key in [
        "high",
        "medium",
        "low",
        "unknown",
    ]:
        print(
            f"{key:10}: {volumes[key]}"
        )

    print()
    print(f"total trades : {total}")


if __name__ == "__main__":
    main()
