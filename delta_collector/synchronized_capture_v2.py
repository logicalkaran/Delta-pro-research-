import json
import signal
import time
from datetime import datetime, timezone
from pathlib import Path

import websocket


URL = "wss://public-socket.india.delta.exchange"
SYMBOL = "BTCUSD"

CHANNELS = [
    "trades",
    "ob_l1",
    "ob_updates",
]

RAW_FILE = "data/raw/delta_btc_research_session_v1.jsonl"

STOP = False
WS = None

COUNTS = {
    "trades": 0,
    "ob_l1": 0,
    "ob_updates": 0,
}


def now():
    return datetime.now(timezone.utc).isoformat()


def shutdown(signum, frame):
    global STOP

    if STOP:
        return

    STOP = True

    print("\n[SHUTDOWN]")

    if WS:
        try:
            WS.close()
        except Exception:
            pass


def save(message):

    path = Path(RAW_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)

    record = {
        "received_at": now(),
        "message": message,
    }

    with path.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                record,
                separators=(",", ":"),
            )
            + "\n"
        )


def on_open(ws):

    print("[CONNECTED]")

    payload = {
        "type": "subscribe",
        "payload": {
            "channels": [
                {
                    "name": channel,
                    "symbols": [SYMBOL],
                }
                for channel in CHANNELS
            ]
        },
    }

    ws.send(json.dumps(payload))

    print(
        "[SUBSCRIBED] "
        + ", ".join(CHANNELS)
    )


def on_message(ws, message):

    if STOP:
        return

    try:

        data = json.loads(message)

        save(data)

        msg_type = data.get("type")

        if msg_type == "trades":

            COUNTS["trades"] += 1

            if COUNTS["trades"] % 100 == 0:
                print(
                    f"[PROGRESS] "
                    f"trades={COUNTS['trades']} "
                    f"l1={COUNTS['ob_l1']} "
                    f"updates={COUNTS['ob_updates']}"
                )

        elif msg_type == "ob_l1":

            COUNTS["ob_l1"] += 1

        elif msg_type == "ob_updates":

            COUNTS["ob_updates"] += 1

        elif msg_type == "subscriptions":

            print("[SUBSCRIPTIONS]")

    except Exception as exc:

        print(f"[PARSE ERROR] {exc}")


def on_error(ws, error):

    if not STOP:
        print(f"[WEBSOCKET ERROR] {error}")


def on_close(ws, code, message):

    print(
        f"[CLOSED] "
        f"code={code} "
        f"message={message}"
    )


if __name__ == "__main__":

    signal.signal(
        signal.SIGINT,
        shutdown,
    )

    signal.signal(
        signal.SIGTERM,
        shutdown,
    )

    print("=" * 60)
    print("DELTA RESEARCH CAPTURE V1")
    print("=" * 60)
    print("Symbol  :", SYMBOL)
    print("Channels:", ", ".join(CHANNELS))
    print("Output  :", RAW_FILE)
    print()
    print("Run for 10-15 minutes, then press Ctrl+C.")
    print()

    WS = websocket.WebSocketApp(
        URL,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
    )

    WS.run_forever(
        ping_interval=20,
        ping_timeout=10,
    )

    print()
    print("[STOPPED]")
    print()
    print("FINAL COUNTS")

    for key, value in COUNTS.items():
        print(f"{key:12}: {value}")
