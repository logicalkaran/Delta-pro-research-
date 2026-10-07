import json
import time
from datetime import datetime, timezone
from pathlib import Path

import websocket

from .config import WS_URL, SYMBOL, CHANNELS, RAW_FILE


STOP = False


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def save_raw(message):
    path = Path(RAW_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)

    record = {
        "received_at": utc_now(),
        "message": message,
    }

    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, separators=(",", ":")) + "\n")


def on_open(ws):
    print("[CONNECTED] Delta WebSocket")

    for channel in CHANNELS:
        payload = {
            "type": "subscribe",
            "payload": {
                "channels": [
                    {
                        "name": channel,
                        "symbols": [SYMBOL],
                    }
                ]
            },
        }

        ws.send(json.dumps(payload))
        print(f"[SUBSCRIBED] {channel}")


def on_message(ws, message):
    try:
        data = json.loads(message)
        save_raw(data)

        print(
            f"[EVENT] type={data.get('type', 'unknown')} "
            f"received={utc_now()}"
        )

    except Exception as exc:
        print(f"[PARSE ERROR] {exc}")


def on_error(ws, error):
    if not STOP:
        print(f"[WEBSOCKET ERROR] {error}")


def on_close(ws, code, message):
    print(f"[CLOSED] code={code} message={message}")


def run():
    global STOP

    while not STOP:
        ws = None

        try:
            print(f"[CONNECTING] {WS_URL}")

            ws = websocket.WebSocketApp(
                WS_URL,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
            )

            ws.run_forever(
                ping_interval=20,
                ping_timeout=10,
            )

        except KeyboardInterrupt:
            STOP = True

            print()
            print("[STOP REQUESTED]")

            if ws:
                try:
                    ws.close()
                except Exception:
                    pass

            break

        except Exception as exc:
            if STOP:
                break

            print(f"[ERROR] {exc}")
            print("[RECONNECTING] in 5 seconds...")

            try:
                time.sleep(5)
            except KeyboardInterrupt:
                STOP = True
                break

    print("[STOPPED] Delta collector shutdown complete")


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("\n[STOPPED] Delta collector shutdown complete")
