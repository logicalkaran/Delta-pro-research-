"""Delta private WebSocket authentication helper using current key-auth."""
from __future__ import annotations
import json, os, time
from execution.delta_signer import sign

PROD_WS = "wss://socket.india.delta.exchange"
DEMO_WS = "wss://socket-ind.testnet.deltaex.org"

def auth_message(environment: str | None = None) -> dict:
    env = (environment or os.getenv("DELTA_ENV", "demo")).lower()
    key = os.getenv("DELTA_API_KEY", "")
    secret = os.getenv("DELTA_API_SECRET", "")
    if not key or not secret:
        raise RuntimeError("Delta credentials are not configured")
    ts = str(int(time.time()))
    return {
        "type": "key-auth",
        "payload": {
            "api-key": key,
            "signature": sign(secret, "GET", ts, "/live"),
            "timestamp": int(ts),
        },
    }

def subscription(channels: list[str]) -> dict:
    if not channels:
        raise ValueError("at least one channel is required")
    return {"type": "subscribe", "payload": {"channels": channels}}
