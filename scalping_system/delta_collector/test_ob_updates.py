import json
import signal
import websocket

URL = "wss://public-socket.india.delta.exchange"

STOP = False


def stop(signum, frame):
    global STOP
    STOP = True
    print("\n[STOP]")
    if ws:
        ws.close()


def on_open(socket):
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

    print("[SENDING]")
    print(json.dumps(payload, indent=2))

    socket.send(json.dumps(payload))


def on_message(socket, message):
    print("\n[RECEIVED]")
    print(message)


def on_error(socket, error):
    print("\n[ERROR]")
    print(repr(error))


def on_close(socket, code, message):
    print("\n[CLOSED]")
    print("code:", code)
    print("message:", message)


ws = None


if __name__ == "__main__":
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    ws = websocket.WebSocketApp(
        URL,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
    )

    ws.run_forever(
        ping_interval=20,
        ping_timeout=10,
    )
