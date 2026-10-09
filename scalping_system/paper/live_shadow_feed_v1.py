"""Bounded live Delta feed for paper/shadow research only.

Connects to public BTCUSD market data, updates compact microstructure and
candle state, and deliberately does NOT persist raw events.
No order API is imported or called.
"""
from __future__ import annotations

import json
import signal
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import websocket

from delta_collector.config import WS_URL, SYMBOL, CHANNELS
from delta_collector.live_state import update as update_live_state
from delta_collector.candle_state import update as update_candles

RUNNING = True


def stop(signum, frame):
    global RUNNING
    RUNNING = False


signal.signal(signal.SIGINT, stop)
signal.signal(signal.SIGTERM, stop)


def on_open(ws):
    print("[CONNECTED] Delta public feed | PAPER ONLY | RAW PERSISTENCE OFF", flush=True)
    for channel in CHANNELS:
        payload = {
            "type": "subscribe",
            "payload": {"channels": [{"name": channel, "symbols": [SYMBOL]}]},
        }
        ws.send(json.dumps(payload))
        print(f"[SUBSCRIBED] {channel}", flush=True)


def on_message(ws, message):
    try:
        data = json.loads(message)
        typ = data.get("type")
        if typ in {"trades", "ob_l1", "ob_l2"}:
            update_live_state(data)
            if typ == "trades":
                update_candles(data)
    except Exception as exc:
        print(f"[PARSE ERROR] {type(exc).__name__}: {exc}", flush=True)


def on_error(ws, error):
    print(f"[WEBSOCKET ERROR] {error}", flush=True)


def on_close(ws, code, msg):
    print(f"[CLOSED] code={code} message={msg}", flush=True)


def run(max_seconds=1800):
    global RUNNING
    started = time.time()
    while RUNNING and time.time() - started < max_seconds:
        try:
            ws = websocket.WebSocketApp(
                WS_URL,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
            )
            ws.run_forever(ping_interval=20, ping_timeout=10)
        except KeyboardInterrupt:
            break
        except Exception as exc:
            print(f"[FEED ERROR] {type(exc).__name__}: {exc}", flush=True)
        if RUNNING and time.time() - started < max_seconds:
            print("[RECONNECTING] 5s", flush=True)
            time.sleep(5)
    print("[STOPPED] bounded paper feed; real orders OFF", flush=True)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=int, default=1800)
    args = ap.parse_args()
    run(args.seconds)
