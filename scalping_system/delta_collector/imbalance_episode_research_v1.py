import json
import statistics
from pathlib import Path


INPUT = Path(
    "data/processed/research_sessions/"
    "btc_research_20260922_095821_canonical_features.jsonl"
)

HORIZONS = [1, 5, 10, 30]

THRESHOLD = 0.60
FRESHNESS_US = 50_000
PERSISTENCE_US = 100_000


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


def is_extreme(row, side):

    age = row.get("book_age_us")

    if age is None or age > FRESHNESS_US:
        return False

    value = float(
        row["l1_imbalance"]
    )

    if side == "positive":
        return value >= THRESHOLD

    return value <= -THRESHOLD


def find_episodes(rows, side):

    episodes = []

    active = False
    start_index = None

    for i in range(len(rows)):

        extreme = is_extreme(
            rows[i],
            side
        )

        if not active:

            if extreme:

                start_ts = rows[i]["trade_ts"]

                end_ts = (
                    start_ts
                    + PERSISTENCE_US
                )

                persistent = True

                for j in range(
                    i + 1,
                    len(rows)
                ):

                    if rows[j]["trade_ts"] > end_ts:
                        break

                    if not is_extreme(
                        rows[j],
                        side
                    ):
                        persistent = False
                        break

                if persistent:

                    episodes.append(i)
                    active = True
                    start_index = i

        else:

            if not extreme:

                active = False
                start_index = None

    return episodes


def main():

    rows = load_rows()

    print("=" * 78)
    print("NON-OVERLAPPING IMBALANCE EPISODE RESEARCH V1")
    print("=" * 78)

    print(f"INPUT ROWS       : {len(rows)}")
    print(f"THRESHOLD        : ±{THRESHOLD:.2f}")
    print(
        f"FRESHNESS        : "
        f"{FRESHNESS_US / 1000:.0f}ms"
    )
    print(
        f"PERSISTENCE      : "
        f"{PERSISTENCE_US / 1000:.0f}ms"
    )

    for side in [
        "positive",
        "negative",
    ]:

        episodes = find_episodes(
            rows,
            side
        )

        print()
        print("=" * 78)
        print(
            f"{side.upper()} EPISODES"
        )
        print("=" * 78)

        print(
            f"episodes : "
            f"{len(episodes)}"
        )

        for horizon in HORIZONS:

            returns = []

            for index in episodes:

                ret = future_return(
                    rows,
                    index,
                    horizon
                )

                if ret is not None:
                    returns.append(ret)

            if returns:

                print(
                    f"{horizon:2d}s "
                    f"N={len(returns):3d} "
                    f"mean="
                    f"{statistics.mean(returns):+.8f}"
                )


if __name__ == "__main__":
    main()
