import json

from .orderbook_v1 import DeltaOrderBook


RAW_FILE = "data/raw/delta_btc_raw.jsonl"


def main():
    book = DeltaOrderBook()

    snapshots = 0
    updates = 0
    checksum_ok = 0
    checksum_failed = 0

    with open(RAW_FILE, encoding="utf-8") as f:
        for line_number, line in enumerate(f, 1):
            try:
                record = json.loads(line)
                message = record["message"]

            except Exception as exc:
                print(f"[BAD JSON] line={line_number}: {exc}")
                continue

            if message.get("type") != "ob_updates":
                continue

            action = message.get("action")

            try:
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
                    book.apply_update(message)
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

                elif action == "error":
                    print(
                        f"[EXCHANGE ERROR] "
                        f"{message.get('msg')}"
                    )

            except Exception as exc:
                print(
                    f"[ORDERBOOK ERROR] "
                    f"line={line_number}: {exc}"
                )

                break

    print()
    print("=" * 60)
    print("ORDER BOOK VALIDATION")
    print("=" * 60)
    print(f"snapshots       : {snapshots}")
    print(f"updates         : {updates}")
    print(f"checksum OK     : {checksum_ok}")
    print(f"checksum failed : {checksum_failed}")
    print(f"final stats     : {book.stats()}")


if __name__ == "__main__":
    main()
