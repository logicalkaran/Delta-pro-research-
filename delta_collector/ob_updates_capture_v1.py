import json
import signal
from datetime import datetime, timezone
from pathlib import Path

import websocket

URL = "wss://public-socket.india.delta.exchange"
RAW_FILE = "data/raw/delta_btc_ob_updates.jsonl"

STOP = False
WS = None


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
        f.write(json.dumps(record, separators=(",", ":")) + "\n")


def on_open(ws):
    print("[CONNECTED]")

    payload = {
        "type": "subscribe",
        "payload": {
            "channels": [
                {
                    "name": "ob_updates",
                    "symbols": ["BTCUSD"],
                }
            ]
        },
    }

    ws.send(json.dumps(payload))
    print("[SUBSCRIBED] ob_updates")


def on_message(ws, message):
    if STOP:
        return

    try:
        data = json.loads(message)
        save(data)

        if data.get("type") == "ob_updates":
            print(
                f"[BOOK] "
                f"action={data.get('action')} "
                f"seq={data.get('seq')} "
                f"cs={data.get('cs')}"
            )
        else:
            print(f"[EVENT] {data.get('type', 'unknown')}")

    except Exception as exc:
        print(f"[PARSE ERROR] {exc}")


def on_error(ws, error):
    if not STOP:
        print(f"[WEBSOCKET ERROR] {error}")


def on_close(ws, code, message):
    print(f"[CLOSED] code={code} message={message}")


if __name__ == "__main__":
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

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

    print("[STOPPED]")
