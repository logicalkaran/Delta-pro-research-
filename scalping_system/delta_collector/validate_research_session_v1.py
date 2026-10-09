import json
import zlib

INPUT_FILE = "data/raw/delta_btc_research_session_v2.jsonl"


def checksum(book):
    asks = sorted(book["asks"].items(), key=lambda x: float(x[0]))[:10]
    bids = sorted(book["bids"].items(), key=lambda x: float(x[0]), reverse=True)[:10]

    ask_text = ",".join(f"{price}:{size}" for price, size in asks)
    bid_text = ",".join(f"{price}:{size}" for price, size in bids)

    payload = ask_text + "|" + bid_text
    return zlib.crc32(payload.encode()) & 0xffffffff


def main():
    book = {"asks": {}, "bids": {}}

    snapshots = 0
    updates = 0
    checksum_ok = 0
    checksum_failed = 0
    sequence_errors = 0

    expected_seq = None

    with open(INPUT_FILE, "r") as f:
        for line in f:
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue

            if msg.get("type") != "ob_updates":
                continue

            asks = msg.get("a", [])
            bids = msg.get("b", [])
            seq = msg.get("seq")
            cs = msg.get("cs")
            action = msg.get("action")

            # First message is the snapshot.
            if snapshots == 0:
                for price, size in asks:
                    if int(size) > 0:
                        book["asks"][price] = int(size)

                for price, size in bids:
                    if int(size) > 0:
                        book["bids"][price] = int(size)

                snapshots += 1
                expected_seq = seq

            else:
                if expected_seq is not None and seq != expected_seq + 1:
                    sequence_errors += 1

                expected_seq = seq

                for price, size in asks:
                    size = int(size)

                    if size == 0:
                        book["asks"].pop(price, None)
                    else:
                        book["asks"][price] = size

                for price, size in bids:
                    size = int(size)

                    if size == 0:
                        book["bids"].pop(price, None)
                    else:
                        book["bids"][price] = size

                updates += 1

            if cs is not None:
                calculated = checksum(book)

                if calculated == int(cs):
                    checksum_ok += 1
                else:
                    checksum_failed += 1

    print("=" * 60)
    print("DELTA RESEARCH SESSION VALIDATION")
    print("=" * 60)

    print(f"snapshots       : {snapshots}")
    print(f"updates         : {updates}")
    print(f"checksum OK     : {checksum_ok}")
    print(f"checksum failed : {checksum_failed}")
    print(f"sequence errors : {sequence_errors}")

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

    print()
    print("FINAL BOOK")
    print("-" * 60)
    print(f"sequence   : {expected_seq}")
    print(f"ask_levels : {len(book['asks'])}")
    print(f"bid_levels : {len(book['bids'])}")
    print(f"best_bid   : {best_bid}")
    print(f"best_ask   : {best_ask}")
    print(f"spread     : {spread}")


if __name__ == "__main__":
    main()
