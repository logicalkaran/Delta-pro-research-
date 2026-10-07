import json
from pathlib import Path

from delta_collector.orderbook_engine_v1 import (
    OrderBookEngine,
)


RAW = Path(
    "data/raw/research_sessions/"
    "btc_research_20260922_095821.jsonl"
)


def main():

    engine = OrderBookEngine()

    snapshots = 0
    updates = 0
    sequence_errors = 0
    states = 0

    with RAW.open() as f:

        for line in f:

            line = line.strip()

            if not line:
                continue

            record = json.loads(line)
            message = record.get("message")

            if not isinstance(message, dict):
                continue

            if message.get("type") != "ob_updates":
                continue

            action = message.get("action")

            try:

                state = (
                    engine.apply_snapshot(message)
                    if action == "snapshot"
                    else engine.apply_update(message)
                )

            except RuntimeError as exc:

                sequence_errors += 1

                print(
                    "ERROR:",
                    exc
                )

                continue

            if action == "snapshot":
                snapshots += 1

            elif action == "update":
                updates += 1

            if state["bid"] is not None:
                states += 1

    print("=" * 70)
    print("ORDER BOOK ENGINE V1 TEST")
    print("=" * 70)

    print(f"snapshots       : {snapshots}")
    print(f"updates         : {updates}")
    print(f"states          : {states}")
    print(f"sequence errors : {sequence_errors}")

    print()
    print("FINAL STATE")
    print("-" * 70)

    final = engine.state()

    for key, value in final.items():
        print(f"{key:16s}: {value}")

    print()

    if (
        snapshots == 1
        and updates == 2964
        and sequence_errors == 0
        and states == 2965
    ):
        print("STATUS          : PASS")
    else:
        print("STATUS          : CHECK")


if __name__ == "__main__":
    main()
