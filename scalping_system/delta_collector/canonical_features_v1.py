import argparse
import json
from pathlib import Path

from delta_collector.orderbook_engine_v1 import OrderBookEngine


DEFAULT_RAW = Path(
    "data/raw/research_sessions/"
    "btc_research_20260922_095821.jsonl"
)

DEFAULT_OUTPUT = Path(
    "data/processed/research_sessions/"
    "btc_research_20260922_095821_canonical_features.jsonl"
)


def load_messages(raw_path):
    messages = []

    with raw_path.open() as f:
        for line in f:
            line = line.strip()

            if not line:
                continue

            record = json.loads(line)
            message = record.get("message")

            if isinstance(message, dict):
                messages.append(message)

    return messages


def canonicalize(raw_path, output_path):
    messages = load_messages(raw_path)

    orderbook = OrderBookEngine()

    book_states = []
    trades = []

    for message in messages:

        message_type = message.get("type")

        if message_type == "ob_updates":

            action = message.get("action")

            if action == "snapshot":
                state = orderbook.apply_snapshot(message)

            elif action == "update":
                state = orderbook.apply_update(message)

            else:
                continue

            book_states.append(state)

        elif message_type == "trades":
            trades.append(message)

    book_states.sort(key=lambda x: x["ts"])
    trades.sort(key=lambda x: x["t"])

    output_rows = []
    book_index = 0
    cumulative_delta = 0.0

    for trade in trades:

        trade_ts = int(trade["t"])
        trade_price = float(trade["p"])
        trade_size = float(trade["s"])

        while (
            book_index + 1 < len(book_states)
            and book_states[book_index + 1]["ts"] <= trade_ts
        ):
            book_index += 1

        if not book_states:
            continue

        state = book_states[book_index]

        if state["ts"] > trade_ts:

            side = "unknown"
            quality = "unknown"
            trade_delta = 0.0
            book_age_us = None

        else:

            bid = state["bid"]
            ask = state["ask"]

            book_age_us = trade_ts - state["ts"]

            if ask is not None and trade_price >= ask:

                side = "buy"
                trade_delta = trade_size
                cumulative_delta += trade_size

            elif bid is not None and trade_price <= bid:

                side = "sell"
                trade_delta = -trade_size
                cumulative_delta -= trade_size

            else:

                side = "unknown"
                trade_delta = 0.0

            if book_age_us <= 20_000:
                quality = "high"

            elif book_age_us <= 50_000:
                quality = "medium"

            elif book_age_us <= 100_000:
                quality = "low"

            else:
                quality = "stale"

        output_rows.append({

            "trade_ts": trade_ts,
            "trade_feed_ts": trade.get("ts"),

            "trade_price": trade["p"],
            "trade_size": trade["s"],
            "role": trade.get("r"),

            "book_ts": state["ts"],
            "book_seq": state["seq"],

            "book_age_us": book_age_us,

            "best_bid": state["bid"],
            "best_bid_size": state["bid_size"],

            "best_ask": state["ask"],
            "best_ask_size": state["ask_size"],

            "mid_price": state["mid"],
            "spread": state["spread"],

            "l1_imbalance": state["l1_imbalance"],
            "l5_imbalance": state["l5_imbalance"],

            "depth_effect": (
                state["l5_imbalance"]
                - state["l1_imbalance"]
                if (
                    state["l5_imbalance"] is not None
                    and state["l1_imbalance"] is not None
                )
                else None
            ),

            "estimated_side": side,
            "quality": quality,

            "trade_delta": trade_delta,
            "cumulative_delta": cumulative_delta,

            "valid_side": side != "unknown",

            "book_valid": (
                state["bid"] is not None
                and state["ask"] is not None
            ),

            "mid_price_valid": state["mid"] is not None,
            "spread_valid": state["spread"] is not None,
        })

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with output_path.open("w") as f:
        for row in output_rows:
            f.write(
                json.dumps(
                    row,
                    separators=(",", ":")
                )
                + "\n"
            )

    quality_counts = {}

    for row in output_rows:
        quality = row["quality"]
        quality_counts[quality] = (
            quality_counts.get(quality, 0) + 1
        )

    print("=" * 70)
    print("CANONICAL FEATURE ENGINE V1")
    print("=" * 70)

    print(f"INPUT        : {raw_path}")
    print(f"trades read  : {len(trades)}")
    print(f"books read   : {len(book_states)}")
    print(f"trades written : {len(output_rows)}")

    print()
    print("QUALITY")

    for key in [
        "high",
        "medium",
        "low",
        "stale",
        "unknown",
    ]:
        print(
            f"{key:10s}: "
            f"{quality_counts.get(key, 0)}"
        )

    print()
    print(f"final CVD    : {cumulative_delta:+.1f}")
    print(f"OUTPUT       : {output_path}")


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_RAW,
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
    )

    args = parser.parse_args()

    canonicalize(
        args.input,
        args.output,
    )


if __name__ == "__main__":
    main()
