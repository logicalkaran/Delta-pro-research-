"""Guarded BTCUSD perpetual live execution controller.

This module connects the validated signal/risk path to Delta production orders.
It is LOCKED unless BTC_LIVE_EXECUTION=true and every live-readiness gate is true.
It never bypasses live_trade_guard.py and never averages into a position.
"""
from __future__ import annotations
import json
import os
import time
from pathlib import Path

from execution.delta_client_private import DeltaAuthClient
from execution.delta_executor import DeltaExecutor, LiveExecutionBlocked
from execution.live_trade_guard import GuardConfig, TradePlan, round_tick, validate

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "data" / "live_microstructure_state.json"
PROFILE = ROOT / "execution" / "LIVE_RISK_PROFILE.json"


def load_state():
    return json.loads(STATE.read_text())


def live_armed() -> bool:
    from execution.live_execution_gate import check
    return bool(check()["eligible"])


def signal(state: dict) -> str | None:
    w5 = state["windows"]["5"]
    w30 = state["windows"]["30"]
    ob = state["order_book"]
    fresh = float(state["quality"]["fresh_seconds"])
    if fresh > 2 or w5["trades"] < 4:
        return None
    long_ok = (
        w5["delta_pct"] >= .12 and w30["delta_pct"] >= .08 and
        ob["imbalance_5"] >= .12 and state["price"]["5"]["return_pct"] >= .025
    )
    short_ok = (
        w5["delta_pct"] <= -.12 and w30["delta_pct"] <= -.08 and
        ob["imbalance_5"] <= -.12 and state["price"]["5"]["return_pct"] <= -.025
    )
    if long_ok and not short_ok:
        return "LONG"
    if short_ok and not long_ok:
        return "SHORT"
    return None


def make_plan(side: str, entry: float, risk_distance: float, rr: float = 2.0) -> TradePlan:
    entry = round_tick(entry)
    risk_distance = round_tick(risk_distance)
    if risk_distance <= 0:
        raise ValueError("risk_distance must be positive")
    target_distance = round_tick(risk_distance * rr)
    if side == "LONG":
        stop, target = round_tick(entry - risk_distance), round_tick(entry + target_distance)
    else:
        stop, target = round_tick(entry + risk_distance), round_tick(entry - target_distance)
    return TradePlan(side, entry, stop, target, 1)


def preflight(risk_distance: float) -> dict:
    profile = json.loads(PROFILE.read_text())
    state = load_state()
    side = signal(state)
    result = {
        "timestamp": time.time(),
        "symbol": "BTCUSD",
        "product_id": 27,
        "mode": "LIVE" if live_armed() else "LOCKED",
        "order_submission": "ARMED" if live_armed() else "DISABLED",
        "signal": side,
        "price": state["order_book"]["mid_price"],
        "fresh_seconds": state["quality"]["fresh_seconds"],
        "reason": None,
    }
    if not side:
        result["reason"] = "NO_VALID_V3_SIGNAL"
        return result
    plan = make_plan(side, float(state["order_book"]["mid_price"]), risk_distance, float(profile["rr"]))
    ok, detail = validate(plan, GuardConfig(
        balance_usd=float(profile["balance_usd"]),
        max_contracts=int(profile["max_contracts"]),
        max_loss_usd=0.35,
        rr=float(profile["rr"]),
    ))
    result["plan"] = plan.__dict__
    result["risk_check"] = detail
    if not ok:
        result["reason"] = str(detail)
        return result
    result["reason"] = "READY_BUT_LOCKED" if not live_armed() else "READY"
    return result


def execute_market(risk_distance: float, client_order_id: str):
    if not live_armed():
        raise LiveExecutionBlocked("BTC_LIVE_EXECUTION is not enabled")
    check = preflight(risk_distance)
    if check.get("reason") != "READY":
        raise LiveExecutionBlocked(json.dumps(check, separators=(",", ":")))

    client = DeltaAuthClient(environment="prod")
    pos = client.get_position("BTCUSD")
    # Do not assume response shape; any non-empty active position blocks a new entry.
    if isinstance(pos, dict):
        data = pos.get("result", pos)
    else:
        data = pos
    if isinstance(data, list):
        active = [p for p in data if float(p.get("size", 0) or 0) != 0]
    elif isinstance(data, dict):
        active = [data] if float(data.get("size", 0) or 0) != 0 else []
    else:
        active = []
    if active:
        raise LiveExecutionBlocked("ACTIVE_POSITION_BLOCK")

    side = "buy" if check["signal"] == "LONG" else "sell"
    executor = DeltaExecutor(client)
    # Entry is the only order submitted here. Stop/target must be placed/verified
    # immediately after a confirmed fill by the position-protection layer.
    return executor.submit_market(
        product_id=27,
        product_symbol="BTCUSD",
        side=side,
        size=1,
        client_order_id=client_order_id,
        reduce_only=False,
        dry_run=False,
    )


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--risk-distance", type=float, required=True)
    ap.add_argument("--client-order-id", default="btc_live_v1")
    ap.add_argument("--preflight", action="store_true")
    args = ap.parse_args()
    if args.preflight:
        print(json.dumps(preflight(args.risk_distance), indent=2))
    else:
        print(json.dumps(execute_market(args.risk_distance, args.client_order_id), indent=2))
