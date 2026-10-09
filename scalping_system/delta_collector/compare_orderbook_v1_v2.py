import json
from pathlib import Path

from delta_collector.orderbook_engine_v1 import OrderBookEngine as V1
from delta_collector.orderbook_engine_v2 import OrderBookEngine as V2


RAW = Path(
    "data/raw/research_sessions/"
    "btc_research_20260922_104858.jsonl"
)


FIELDS = [
    "seq",
    "ts",
    "bid",
    "bid_size",
    "ask",
    "ask_size",
    "mid",
    "spread",
    "l1_imbalance",
    "l5_imbalance",
    "bid_levels",
    "ask_levels",
]


def same(a, b):
    if a is None and b is None:
        return True

    if isinstance(a, float) and isinstance(b, float):
        return abs(a - b) <= 1e-12

    return a == b


def compare_states(a, b):
    differences = []

    for field in FIELDS:
        av = a.get(field)
        bv = b.get(field)

        if not same(av, bv):
            differences.append(
                (field, av, bv)
            )

    return differences


def main():
    print("=" * 70)
    print("ORDER BOOK V1 vs V2 CORRECTNESS TEST")
    print("=" * 70)
    print(f"Input: {RAW}")

    if not RAW.exists():
        print("ERROR: input file not found")
        return

    v1 = V1()
    v2 = V2()

    messages = 0
    book_messages = 0
    compared = 0
    mismatches = 0
    errors = 0

    first_mismatch = None

    with RAW.open() as f:
        for line_number, line in enumerate(f, 1):

            if not line.strip():
                continue

            try:
                record = json.loads(line)
            except Exception:
                errors += 1
                continue

            message = record.get("message")

            if not isinstance(message, dict):
                continue

            messages += 1

            if message.get("type") != "ob_updates":
                continue

            action = message.get("action")

            if action not in ("snapshot", "update"):
                continue

            book_messages += 1

            try:
                if action == "snapshot":
                    state1 = v1.apply_snapshot(message)
                    state2 = v2.apply_snapshot(message)
                else:
                    state1 = v1.apply_update(message)
                    state2 = v2.apply_update(message)

            except Exception as exc:
                errors += 1

                if first_mismatch is None:
                    first_mismatch = (
                        line_number,
                        "EXCEPTION",
                        str(exc),
                    )

                continue

            compared += 1

            differences = compare_states(
                state1,
                state2
            )

            if differences:
                mismatches += 1

                if first_mismatch is None:
                    first_mismatch = (
                        line_number,
                        "STATE MISMATCH",
                        differences,
                    )

    print()
    print("RESULTS")
    print("-" * 70)
    print(f"Messages read       : {messages}")
    print(f"Book messages       : {book_messages}")
    print(f"States compared     : {compared}")
    print(f"Mismatches          : {mismatches}")
    print(f"Errors              : {errors}")

    print()

    if mismatches == 0 and errors == 0:
        print("STATUS: PASS")
        print("V2 matches V1 for every compared order-book state.")
    else:
        print("STATUS: FAIL")

        if first_mismatch:
            print()
            print("FIRST PROBLEM")
            print(f"Line       : {first_mismatch[0]}")
            print(f"Type       : {first_mismatch[1]}")
            print(f"Details    : {first_mismatch[2]}")

    print("=" * 70)


if __name__ == "__main__":
    main()
