import json
import statistics
from pathlib import Path


INPUT = Path(
    "data/processed/research_sessions/"
    "btc_research_20260922_095821_canonical_features.jsonl"
)

HORIZONS = [1, 5, 10, 30]


def load_rows():

    rows = []

    with INPUT.open() as f:

        for line in f:

            line = line.strip()

            if not line:
                continue

            row = json.loads(line)

            if (
                row.get("l1_imbalance") is None
                or row.get("mid_price") is None
                or row.get("best_bid") is None
                or row.get("best_ask") is None
            ):
                continue

            rows.append(row)

    rows.sort(
        key=lambda x: x["trade_ts"]
    )

    return rows


def future_return(rows, index, seconds):

    target = (
        rows[index]["trade_ts"]
        + seconds * 1_000_000
    )

    current = float(
        rows[index]["mid_price"]
    )

    for j in range(index + 1, len(rows)):

        if rows[j]["trade_ts"] >= target:

            future = float(
                rows[j]["mid_price"]
            )

            return (
                future / current
            ) - 1.0

    return None


def classify(value):

    if value >= 0.60:
        return "strong_positive"

    if value >= 0.20:
        return "positive"

    if value > -0.20:
        return "neutral"

    if value > -0.60:
        return "negative"

    return "strong_negative"


def main():

    rows = load_rows()

    print("=" * 78)
    print("IMBALANCE PERSISTENCE RESEARCH V1")
    print("=" * 78)

    print(f"INPUT ROWS : {len(rows)}")

    for age_limit in [
        None,
        100_000,
        50_000,
    ]:

        age_name = (
            "all"
            if age_limit is None
            else f"{age_limit // 1000}ms"
        )

        print()
        print("=" * 78)
        print(f"BOOK AGE FILTER: {age_name}")
        print("=" * 78)

        for persistence in [1, 2, 3]:

            print()
            print(
                f"PERSISTENCE = "
                f"{persistence}"
            )

            for target_bucket in [
                "strong_positive",
                "strong_negative",
            ]:

                indices = []

                for i in range(
                    persistence - 1,
                    len(rows)
                ):

                    valid = True

                    for k in range(
                        persistence
                    ):

                        row = rows[i - k]

                        age = row.get(
                            "book_age_us"
                        )

                        if (
                            age_limit is not None
                            and (
                                age is None
                                or age > age_limit
                            )
                        ):
                            valid = False
                            break

                    if not valid:
                        continue

                    current_bucket = classify(
                        float(
                            rows[i][
                                "l1_imbalance"
                            ]
                        )
                    )

                    if current_bucket != target_bucket:
                        continue

                    same_bucket = True

                    for k in range(
                        1,
                        persistence
                    ):

                        previous_bucket = classify(
                            float(
                                rows[i - k][
                                    "l1_imbalance"
                                ]
                            )
                        )

                        if (
                            previous_bucket
                            != target_bucket
                        ):
                            same_bucket = False
                            break

                    if same_bucket:
                        indices.append(i)

                print()
                print(
                    f"{target_bucket}"
                )

                print(
                    f"events : {len(indices)}"
                )

                for horizon in HORIZONS:

                    returns = []

                    for i in indices:

                        ret = future_return(
                            rows,
                            i,
                            horizon
                        )

                        if ret is not None:
                            returns.append(ret)

                    if returns:

                        print(
                            f"  {horizon:2d}s "
                            f"N={len(returns):3d} "
                            f"mean="
                            f"{statistics.mean(returns):+.8f}"
                        )


if __name__ == "__main__":
    main()
