import json
import zlib

INPUT_FILE = "data/raw/delta_btc_research_session_v2.jsonl"


def calculate_checksum(book):
    asks = sorted(
        book["asks"].items(),
        key=lambda x: float(x[0])
    )[:10]

    bids = sorted(
        book["bids"].items(),
        key=lambda x: float(x[0]),
        reverse=True
    )[:10]

    ask_text = ",".join(
        f"{price}:{size}"
        for price, size in asks
    )

    bid_text = ",".join(
        f"{price}:{size}"
        for price, size in bids
    )

    payload = ask_text + "|" + bid_text

    return zlib.crc32(payload.encode()) & 0xffffffff


def apply_levels(levels, book_side):
    for price, size in levels:
        size = int(size)

        if size == 0:
            book_side.pop(price, None)
        else:
            book_side[price] = size


def main():
    book = {
        "asks": {},
        "bids": {},
    }

    snapshots = 0
    updates = 0
    checksum_ok = 0
    checksum_failed = 0
    sequence_errors = 0

    first_sequence = None
    last_sequence = None
    previous_sequence = None

    message_counts = {}

    with open(INPUT_FILE, "r") as f:
        for line_no, line in enumerate(f, 1):

            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            message = record.get("message")

            if not isinstance(message, dict):
                continue

            msg_type = message.get("type")

            message_counts[msg_type] = (
                message_counts.get(msg_type, 0) + 1
            )

            if msg_type != "ob_updates":
                continue

            sequence = message.get("seq")
            checksum = message.get("cs")

            asks = message.get("a", [])
            bids = message.get("b", [])

            if snapshots == 0:
                if message.get("action") != "snapshot":
                    print(
                        f"ERROR: first ob_updates message "
                        f"is not snapshot at line {line_no}"
                    )
                    return

                apply_levels(asks, book["asks"])
                apply_levels(bids, book["bids"])

                snapshots = 1
                first_sequence = sequence
                previous_sequence = sequence
                last_sequence = sequence

            else:
                if (
                    previous_sequence is not None
                    and sequence != previous_sequence + 1
                ):
                    sequence_errors += 1

                apply_levels(asks, book["asks"])
                apply_levels(bids, book["bids"])

                updates += 1

                previous_sequence = sequence
                last_sequence = sequence

            if checksum is not None:
                calculated = calculate_checksum(book)

                if calculated == int(checksum):
                    checksum_ok += 1
                else:
                    checksum_failed += 1

    if book["bids"]:
        best_bid = max(book["bids"], key=float)
    else:
        best_bid = None

    if book["asks"]:
        best_ask = min(book["asks"], key=float)
    else:
        best_ask = None

    spread = None

    if best_bid is not None and best_ask is not None:
        spread = float(best_ask) - float(best_bid)

    print("=" * 60)
    print("DELTA RESEARCH SESSION VALIDATION V2")
    print("=" * 60)

    print()
    print("MESSAGE COUNTS")
    print("-" * 60)

    for key, value in sorted(
        message_counts.items(),
        key=lambda x: str(x[0])
    ):
        print(f"{str(key):15} : {value}")

    print()
    print("ORDER BOOK VALIDATION")
    print("-" * 60)

    print(f"snapshots       : {snapshots}")
    print(f"updates         : {updates}")
    print(f"checksum OK     : {checksum_ok}")
    print(f"checksum failed : {checksum_failed}")
    print(f"sequence errors : {sequence_errors}")

    print()
    print("SEQUENCE")
    print("-" * 60)

    print(f"first sequence  : {first_sequence}")
    print(f"last sequence   : {last_sequence}")

    print()
    print("FINAL BOOK")
    print("-" * 60)

    print(f"ask_levels      : {len(book['asks'])}")
    print(f"bid_levels      : {len(book['bids'])}")
    print(f"best_bid        : {best_bid}")
    print(f"best_ask        : {best_ask}")
    print(f"spread          : {spread}")


if __name__ == "__main__":
    main()
