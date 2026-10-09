import json
import signal
import time
from datetime import datetime, timezone
from pathlib import Path

import websocket

from .config import WS_URL, SYMBOL, CHANNELS, RAW_FILE


STOP = False
CURRENT_WS = None


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def shutdown(signum, frame):
    global STOP, CURRENT_WS

    if STOP:
        return

    STOP = True
    print("\n[SHUTDOWN] Ctrl+C received")

    if CURRENT_WS is not None:
        try:
            CURRENT_WS.close()
        except Exception:
            pass


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
    if STOP:
        return

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
    global CURRENT_WS

    while not STOP:

        try:
            print(f"[CONNECTING] {WS_URL}")

            CURRENT_WS = websocket.WebSocketApp(
                WS_URL,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
            )

            CURRENT_WS.run_forever(
                ping_interval=20,
                ping_timeout=10,
            )

        except Exception as exc:
            if STOP:
                break

            print(f"[ERROR] {exc}")
            print("[RECONNECTING] in 5 seconds...")

            try:
                time.sleep(5)
            except KeyboardInterrupt:
                shutdown(None, None)

        finally:
            CURRENT_WS = None

        if STOP:
            break

    print("[STOPPED] Delta collector shutdown complete")


if __name__ == "__main__":
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    run()
