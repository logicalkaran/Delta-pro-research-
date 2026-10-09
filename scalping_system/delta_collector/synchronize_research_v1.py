import bisect
import json
from collections import defaultdict

INPUT_FILE = "data/raw/delta_btc_research_session_v2.jsonl"
OUTPUT_FILE = "data/processed/btc_research_synchronized_v1.jsonl"


def apply_levels(book_side, levels):
    for price, size in levels:
        size = int(size)

        if size == 0:
            book_side.pop(price, None)
        else:
            book_side[price] = size


def best_bid(book):
    if not book["bids"]:
        return None
    return max(book["bids"], key=float)


def best_ask(book):
    if not book["asks"]:
        return None
    return min(book["asks"], key=float)


def depth(book, side, levels=5):
    items = list(book[side].items())

    if side == "bids":
        items.sort(key=lambda x: float(x[0]), reverse=True)
    else:
        items.sort(key=lambda x: float(x[0]))

    return sum(
        int(size)
        for _, size in items[:levels]
    )


def imbalance(book, levels=5):
    bid_depth = depth(book, "bids", levels)
    ask_depth = depth(book, "asks", levels)

    total = bid_depth + ask_depth

    if total == 0:
        return None

    return (bid_depth - ask_depth) / total


def classify_trade(price, bid, ask):
    if bid is None or ask is None:
        return "unknown"

    price = float(price)
    bid = float(bid)
    ask = float(ask)

    if price >= ask:
        return "buy"

    if price <= bid:
        return "sell"

    return "unknown"


def load_events():
    trades = []
    updates = []

    with open(INPUT_FILE, "r") as f:
        for line in f:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            message = record.get("message")

            if not isinstance(message, dict):
                continue

            msg_type = message.get("type")

            if msg_type == "trades":
                trades.append(message)

            elif msg_type == "ob_updates":
                updates.append(message)

    trades.sort(key=lambda x: x.get("t", 0))
    updates.sort(key=lambda x: x.get("ts", 0))

    return trades, updates


def build_book_states(updates):
    if not updates:
        return [], []

    book = {
        "asks": {},
        "bids": {},
    }

    timestamps = []
    states = []

    for i, update in enumerate(updates):

        asks = update.get("a", [])
        bids = update.get("b", [])

        if i == 0:
            if update.get("action") != "snapshot":
                raise RuntimeError(
                    "First ob_updates message is not a snapshot"
                )

            apply_levels(book["asks"], asks)
            apply_levels(book["bids"], bids)

        else:
            apply_levels(book["asks"], asks)
            apply_levels(book["bids"], bids)

        ts = update.get("ts")

        timestamps.append(ts)

        states.append({
            "ts": ts,
            "seq": update.get("seq"),
            "asks": dict(book["asks"]),
            "bids": dict(book["bids"]),
        })

    return timestamps, states


def main():
    trades, updates = load_events()

    timestamps, states = build_book_states(updates)

    if not timestamps:
        raise RuntimeError("No order-book updates found")

    synchronized = []

    for trade in trades:
        trade_ts = trade.get("t")

        if trade_ts is None:
            continue

        index = bisect.bisect_right(
            timestamps,
            trade_ts
        ) - 1

        if index < 0:
            book_age = None
            state = None
        else:
            state = states[index]
            book_age = trade_ts - state["ts"]

        if state is None:
            bid = None
            ask = None
            mid = None
            spread = None
            imbalance_5 = None
            side = "unknown"
            seq = None

        else:
            book = state

            bid = best_bid(book)
            ask = best_ask(book)

            if bid is not None and ask is not None:
                bid_f = float(bid)
                ask_f = float(ask)

                mid = (bid_f + ask_f) / 2
                spread = ask_f - bid_f
            else:
                mid = None
                spread = None

            imbalance_5 = imbalance(book, 5)

            side = classify_trade(
                trade.get("p"),
                bid,
                ask
            )

            seq = state["seq"]

        synchronized.append({
            "trade_ts": trade_ts,
            "trade_feed_ts": trade.get("ts"),
            "trade_price": trade.get("p"),
            "trade_size": trade.get("s"),
            "role": trade.get("r"),
            "book_ts": None if state is None else state["ts"],
            "book_seq": seq,
            "book_age_us": book_age,
            "best_bid": bid,
            "best_ask": ask,
            "mid_price": mid,
            "spread": spread,
            "imbalance_5": imbalance_5,
            "estimated_side": side,
        })

    with open(OUTPUT_FILE, "w") as f:
        for row in synchronized:
            f.write(json.dumps(row) + "\n")

    side_counts = defaultdict(int)

    ages = []

    for row in synchronized:
        side_counts[row["estimated_side"]] += 1

        if row["book_age_us"] is not None:
            ages.append(row["book_age_us"])

    print("=" * 60)
    print("DELTA RESEARCH SYNCHRONIZATION V1")
    print("=" * 60)

    print()
    print(f"trades             : {len(trades)}")
    print(f"book updates       : {len(updates)}")
    print(f"synchronized       : {len(synchronized)}")

    print()
    print("ESTIMATED SIDE")
    print("-" * 60)

    for side in ("buy", "sell", "unknown"):
        print(f"{side:18} : {side_counts[side]}")

    print()

    if ages:
        print("BOOK AGE")
        print("-" * 60)
        print(f"min book age us    : {min(ages)}")
        print(f"max book age us    : {max(ages)}")
        print(f"avg book age us    : {sum(ages) / len(ages):.1f}")
        print(f"future quote count : {sum(1 for x in ages if x < 0)}")

    print()
    print(f"output             : {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
