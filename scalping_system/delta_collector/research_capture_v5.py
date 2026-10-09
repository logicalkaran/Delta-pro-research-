import asyncio
import json
import signal
import time
from pathlib import Path

import websockets


URL = "wss://public-socket.india.delta.exchange"

OUTPUT_DIR = Path(
    "data/raw/research_sessions"
)

TARGET_TRADES = 5000


stop_requested = False


def request_stop():
    global stop_requested
    stop_requested = True
    print("\nSTOP REQUESTED — finishing cleanly...")


async def capture():

    global stop_requested

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    timestamp = time.strftime(
        "%Y%m%d_%H%M%S"
    )

    output = (
        OUTPUT_DIR
        / f"btc_research_{timestamp}.jsonl"
    )

    signal.signal(
        signal.SIGINT,
        lambda *_: request_stop()
    )

    signal.signal(
        signal.SIGTERM,
        lambda *_: request_stop()
    )

    trades = 0
    messages = 0

    print("=" * 70)
    print("DELTA RESEARCH CAPTURE V5")
    print("=" * 70)
    print(f"Target trades : {TARGET_TRADES}")
    print(f"Output        : {output}")
    print()

    async with websockets.connect(
        URL,
        ping_interval=20,
        ping_timeout=20,
        max_size=None,
    ) as ws:

        subscriptions = {
            "type": "subscribe",
            "payload": {
                "channels": [
                    {
                        "name": "trades",
                        "symbols": ["BTCUSD"],
                    },
                    {
                        "name": "ob_updates",
                        "symbols": ["BTCUSD"],
                    },
                ]
            },
        }

        await ws.send(
            json.dumps(subscriptions)
        )

        with output.open("w") as f:

            while (
                not stop_requested
                and trades < TARGET_TRADES
            ):

                try:

                    raw = await asyncio.wait_for(
                        ws.recv(),
                        timeout=5,
                    )

                except asyncio.TimeoutError:

                    continue

                if not raw:
                    continue

                try:
                    message = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                record = {
                    "received_at":
                        time.time_ns(),
                    "message":
                        message,
                }

                f.write(
                    json.dumps(record)
                    + "\n"
                )

                f.flush()

                messages += 1

                if message.get("type") == "trades":

                    trades += 1

                    if trades % 500 == 0:

                        print(
                            f"trades={trades} "
                            f"messages={messages}"
                        )

    print()
    print("=" * 70)
    print("CAPTURE COMPLETE")
    print("=" * 70)
    print(f"Trades    : {trades}")
    print(f"Messages  : {messages}")
    print(f"Output    : {output}")


if __name__ == "__main__":

    try:
        asyncio.run(capture())

    except KeyboardInterrupt:

        # Fallback if the signal handler is bypassed.
        print(
            "\nCapture interrupted safely."
        )
