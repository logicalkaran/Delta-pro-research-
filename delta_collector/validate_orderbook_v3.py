import json

from .orderbook_v2 import DeltaOrderBook


RAW_FILE = "data/raw/delta_btc_ob_updates.jsonl"


def main():
    book = DeltaOrderBook()

    snapshots = 0
    updates = 0
    checksum_ok = 0
    checksum_failed = 0
    sequence_errors = 0

    with open(RAW_FILE, encoding="utf-8") as f:
        for line_number, line in enumerate(f, 1):

            record = json.loads(line)
            message = record["message"]

            if message.get("type") != "ob_updates":
                continue

            action = message.get("action")

            if action == "snapshot":

                book.load_snapshot(message)
                snapshots += 1

                print(
                    f"[SNAPSHOT] "
                    f"seq={book.last_seq} "
                    f"asks={len(book.asks)} "
                    f"bids={len(book.bids)}"
                )

            elif action == "update":

                try:
                    book.apply_update(message)

                except RuntimeError as exc:
                    sequence_errors += 1

                    print(
                        f"[SEQUENCE ERROR] "
                        f"line={line_number}: {exc}"
                    )

                    break

                updates += 1

                if book.verify_checksum(message["cs"]):

                    checksum_ok += 1

                else:

                    checksum_failed += 1

                    print(
                        f"[CHECKSUM FAIL] "
                        f"seq={message['seq']} "
                        f"expected={message['cs']} "
                        f"actual={book.checksum()}"
                    )

                    print(
                        f"checksum_string="
                        f"{book.checksum_string()}"
                    )

    print()
    print("=" * 60)
    print("DELTA ORDER BOOK VALIDATION V3")
    print("=" * 60)

    print(f"snapshots       : {snapshots}")
    print(f"updates         : {updates}")
    print(f"checksum OK     : {checksum_ok}")
    print(f"checksum failed : {checksum_failed}")
    print(f"sequence errors : {sequence_errors}")

    print()
    print("FINAL BOOK")
    print("-" * 60)
    print(book.stats())


if __name__ == "__main__":
    main()
