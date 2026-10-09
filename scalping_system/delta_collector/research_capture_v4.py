import asyncio
import json
import time
from pathlib import Path

import websockets


WS_URL = "wss://public-socket.india.delta.exchange"

SYMBOL = "BTCUSD"

TARGET_TRADES = 10_000

OUTPUT_DIR = Path("data/raw/research_sessions")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def session_path():
    stamp = time.strftime("%Y%m%d_%H%M%S")
    return OUTPUT_DIR / f"btc_research_{stamp}.jsonl"


async def capture():
    output = session_path()

    trade_count = 0
    message_count = 0

    print("=" * 70)
    print("DELTA RESEARCH CAPTURE V4")
    print("=" * 70)
    print(f"Symbol       : {SYMBOL}")
    print(f"Target trades: {TARGET_TRADES}")
    print(f"Output       : {output}")
    print()

    async with websockets.connect(
        WS_URL,
        ping_interval=20,
        ping_timeout=20,
        close_timeout=5,
        max_size=None,
    ) as ws:

        subscriptions = {
            "type": "subscribe",
            "payload": {
                "channels": [
                    {
                        "name": "trades",
                        "symbols": [SYMBOL],
                    },
                    {
                        "name": "ob_updates",
                        "symbols": [SYMBOL],
                    },
                ]
            },
        }

        await ws.send(json.dumps(subscriptions))

        print("Subscription sent.")
        print("Capturing...")
        print("Press Ctrl+C for a graceful stop.")
        print()

        with output.open("w") as f:

            metadata = {
                "record_type": "research_session_start",
                "started_at": time.time(),
                "symbol": SYMBOL,
                "target_trades": TARGET_TRADES,
                "ws_url": WS_URL,
            }

            f.write(json.dumps(metadata) + "\n")
            f.flush()

            try:
                while trade_count < TARGET_TRADES:

                    raw = await ws.recv()

                    received_at = time.time_ns()

                    message_count += 1

                    try:
                        message = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    record = {
                        "received_at_ns": received_at,
                        "message": message,
                    }

                    f.write(json.dumps(record) + "\n")

                    message_type = message.get("type")

                    if message_type == "trades":
                        trade_count += 1

                        if trade_count % 100 == 0:
                            print(
                                f"trades={trade_count:5d} "
                                f"messages={message_count:7d}"
                            )

                    if message_count % 100 == 0:
                        f.flush()

            except KeyboardInterrupt:
                print()
                print("Graceful stop requested.")

            finally:
                f.flush()

                end_metadata = {
                    "record_type": "research_session_end",
                    "ended_at": time.time(),
                    "trade_count": trade_count,
                    "message_count": message_count,
                }

                f.write(json.dumps(end_metadata) + "\n")

    print()
    print("=" * 70)
    print("CAPTURE COMPLETE")
    print("=" * 70)
    print(f"Trades captured : {trade_count}")
    print(f"Messages        : {message_count}")
    print(f"File            : {output}")


if __name__ == "__main__":
    asyncio.run(capture())
