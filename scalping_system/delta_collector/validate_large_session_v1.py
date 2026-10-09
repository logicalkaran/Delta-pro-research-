import json
import sys
import zlib
from pathlib import Path


if len(sys.argv) != 2:
    print("Usage:")
    print(
        "python -m delta_collector.validate_large_session_v1 "
        "<jsonl_file>"
    )
    raise SystemExit(1)


PATH = Path(sys.argv[1])


def checksum(book):
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

    payload = f"{ask_text}|{bid_text}"

    return zlib.crc32(
        payload.encode()
    )


def main():
    messages = 0
    trades = 0
    snapshots = 0
    updates = 0

    checksum_ok = 0
    checksum_failed = 0
    sequence_errors = 0

    first_seq = None
    last_seq = None

    asks = {}
    bids = {}

    with PATH.open() as f:

        for line in f:

            line = line.strip()

            if not line:
                continue

            record = json.loads(line)
            message = record.get("message")

            if not isinstance(message, dict):
                continue

            messages += 1

            message_type = message.get("type")

            if message_type == "trades":
                trades += 1
                continue

            if message_type != "ob_updates":
                continue

            action = message.get("action")
            seq = message.get("seq")
            expected = message.get("cs")

            if action == "snapshot":

                snapshots += 1

                asks.clear()
                bids.clear()

                for price, size in message.get("a", []):
                    size = int(size)

                    if size > 0:
                        asks[price] = size

                for price, size in message.get("b", []):
                    size = int(size)

                    if size > 0:
                        bids[price] = size

                first_seq = seq
                last_seq = seq

            elif action == "update":

                updates += 1

                if last_seq is not None:
                    if seq != last_seq + 1:
                        sequence_errors += 1

                last_seq = seq

                for price, size in message.get("a", []):
                    size = int(size)

                    if size == 0:
                        asks.pop(price, None)
                    else:
                        asks[price] = size

                for price, size in message.get("b", []):
                    size = int(size)

                    if size == 0:
                        bids.pop(price, None)
                    else:
                        bids[price] = size

            else:
                continue

            if expected is not None:
                actual = checksum({
                    "asks": asks,
                    "bids": bids,
                })

                if actual == int(expected):
                    checksum_ok += 1
                else:
                    checksum_failed += 1

    print("=" * 72)
    print("LARGE RESEARCH SESSION VALIDATION V1")
    print("=" * 72)

    print()
    print("FILE")
    print(f"{PATH}")

    print()
    print("MESSAGE COUNTS")
    print(f"total messages   : {messages}")
    print(f"trades           : {trades}")
    print(f"ob snapshots     : {snapshots}")
    print(f"ob updates       : {updates}")

    print()
    print("ORDER BOOK VALIDATION")
    print(f"checksum OK      : {checksum_ok}")
    print(f"checksum failed  : {checksum_failed}")
    print(f"sequence errors  : {sequence_errors}")

    print()
    print("SEQUENCE")
    print(f"first sequence   : {first_seq}")
    print(f"last sequence    : {last_seq}")

    print()
    print("FINAL BOOK")
    print(f"ask levels       : {len(asks)}")
    print(f"bid levels       : {len(bids)}")

    if asks and bids:
        best_ask = min(
            float(price)
            for price in asks
        )

        best_bid = max(
            float(price)
            for price in bids
        )

        print(f"best bid         : {best_bid}")
        print(f"best ask         : {best_ask}")
        print(f"spread           : {best_ask - best_bid}")

    print()
    if checksum_failed == 0 and sequence_errors == 0:
        print("STATUS           : PASS")
    else:
        print("STATUS           : FAIL")


if __name__ == "__main__":
    main()
