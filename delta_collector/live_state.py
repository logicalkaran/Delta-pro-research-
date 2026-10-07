"""Atomic live market-state writer for the dashboard."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from .microstructure import update as update_microstructure

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "data" / "live_market_state.json"


def update(message):
    if not isinstance(message, dict):
        return
    data = {}
    if STATE.exists():
        try:
            data = json.loads(STATE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    typ = message.get("type")
    data["symbol"] = message.get("sy", data.get("symbol", "BTCUSD"))
    data["updated_at"] = int(time.time())
    data["event_type"] = typ
    if typ == "trades":
        try:
            price = float(message["p"])
            size = float(message.get("s", 0))
            data["last_price"] = price
            data["last_trade_size"] = size
            data["last_trade_side"] = "sell" if message.get("r") == "m" else "buy"
        except (TypeError, ValueError, KeyError):
            pass
    elif typ == "ob_l1":
        try:
            ask = float(message["ap"])
            bid = float(message["bp"])
            data["best_ask"] = ask
            data["best_bid"] = bid
            data["mid_price"] = (ask + bid) / 2
            data["spread"] = ask - bid
            data["ask_size"] = float(message.get("as", 0))
            data["bid_size"] = float(message.get("bs", 0))
        except (TypeError, ValueError, KeyError):
            pass

    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, STATE)

    # Read-only analytics sidecar. It has no execution capability.
    try:
        update_microstructure(message)
    except Exception as exc:
        print(f"[MICROSTRUCTURE] {type(exc).__name__}: {exc}")
