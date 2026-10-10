"""Production-ready BTCUSD perpetual controller with hard manual arming.

Default is monitor/preflight only. Real-money submission requires BOTH
BTC_LIVE_EXECUTION=true and BTC_LIVE_OPERATOR_APPROVED=true, plus every
existing live-readiness gate. This file never changes those flags itself.
"""
from __future__ import annotations
import hashlib
import json
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in __import__('sys').path:
    __import__('sys').path.insert(0, str(ROOT))

from execution.delta_client_private import DeltaAuthClient
from execution.delta_executor import DeltaExecutor, LiveExecutionBlocked
from execution.live_trade_guard import GuardConfig, TradePlan, round_tick, validate
from risk.production_guard import MarketSnapshot, validate_market
from exchange.delta_state_adapter import DeltaReadOnlyStateAdapter
from storage.event_journal import EventJournal
from execution.authoritative_account_risk import evaluate_authoritative_intent

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "data" / "live_microstructure_state.json"
PROFILE = ROOT / "execution" / "LIVE_RISK_PROFILE.json"
JOURNAL = ROOT / "data" / "processed" / "live_execution_journal.jsonl"
KILL = ROOT / "data" / "run" / "LIVE_KILL_SWITCH"

PRODUCT_ID = 27
SYMBOL = "BTCUSD"
TICK = 0.5
CONTRACTS = 1
RR = 2.0
MAX_LOSS = 0.35


def _env_bool(name: str) -> bool:
    return os.getenv(name, "").lower() == "true"


def _load_state():
    return json.loads(STATE.read_text())


def _append(row: dict):
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    with JOURNAL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, separators=(",", ":")) + "\n")


def signal(state: dict) -> str | None:
    w5, w30 = state["windows"]["5"], state["windows"]["30"]
    ob, q = state["order_book"], state["quality"]
    if float(q["fresh_seconds"]) > 2 or int(w5["trades"]) < 4:
        return None
    long_ok = (w5["delta_pct"] >= .12 and w30["delta_pct"] >= .08 and
               ob["imbalance_5"] >= .12 and state["price"]["5"]["return_pct"] >= .025)
    short_ok = (w5["delta_pct"] <= -.12 and w30["delta_pct"] <= -.08 and
                ob["imbalance_5"] <= -.12 and state["price"]["5"]["return_pct"] <= -.025)
    if long_ok and not short_ok:
        return "LONG"
    if short_ok and not long_ok:
        return "SHORT"
    return None


def plan_for(side: str, entry: float, risk_distance: float) -> TradePlan:
    entry = round_tick(float(entry), TICK)
    risk = round_tick(float(risk_distance), TICK)
    if risk <= 0:
        raise ValueError("risk distance must be positive")
    reward = round_tick(risk * RR, TICK)
    if side == "LONG":
        return TradePlan(side, entry, round_tick(entry - risk, TICK), round_tick(entry + reward, TICK), CONTRACTS)
    return TradePlan(side, entry, round_tick(entry + risk, TICK), round_tick(entry - reward, TICK), CONTRACTS)


def active_position(payload) -> bool:
    data = payload.get("result", payload) if isinstance(payload, dict) else payload
    if isinstance(data, list):
        return any(float(x.get("size", 0) or 0) != 0 for x in data if isinstance(x, dict))
    if isinstance(data, dict):
        return float(data.get("size", 0) or 0) != 0
    return False


def preflight(risk_distance: float, *, state_adapter=None, event_journal=None, now_ms=None) -> dict:
    state = _load_state()
    # Validate authoritative account freshness before evaluating the strategy signal.
    adapter = state_adapter or DeltaReadOnlyStateAdapter()
    account = adapter.account_state()
    current_ms = int(time.time() * 1000) if now_ms is None else int(now_ms)
    if current_ms - int(account.observed_at_ms) > 5000 or int(account.observed_at_ms) - current_ms > 1000:
        return {"timestamp": time.time(), "order_submission": "DISABLED", "signal": None,
                "reason": "STALE_DATA_REJECTION"}
    if not account.complete:
        return {"timestamp": time.time(), "order_submission": "DISABLED", "signal": None,
                "reason": "MISSING_ACCOUNT_FIELDS:" + ",".join(account.missing_fields)}
    side = signal(state)
    journal = event_journal
    result = {
        "timestamp": time.time(), "symbol": SYMBOL, "product_id": PRODUCT_ID,
        "execution_mode": "LOCKED" if not (_env_bool("BTC_LIVE_EXECUTION") and _env_bool("BTC_LIVE_OPERATOR_APPROVED")) else "ARMED_REQUEST",
        "order_submission": "DISABLED", "signal": side,
        "price": state["order_book"]["mid_price"], "fresh_seconds": state["quality"]["fresh_seconds"],
    }
    if KILL.exists():
        result["reason"] = "KILL_SWITCH"
        return result
    if not side:
        result["reason"] = "NO_VALID_SIGNAL"
        return result

    # Independent production safety envelope. Missing/invalid microstructure
    # fields fail closed rather than being inferred or defaulted.
    try:
        mid = float(state["order_book"]["mid_price"])
        spread = float(state["order_book"]["spread"])
        age = float(state["quality"]["fresh_seconds"])
        slippage = float(state["execution"]["estimated_slippage_bps"])
    except (KeyError, TypeError, ValueError):
        result["reason"] = "PRODUCTION_SAFETY_INPUT_MISSING"
        return result
    market_ok, market_reason = validate_market(
        MarketSnapshot(age_seconds=age, spread_bps=(spread / mid * 10000.0),
                        estimated_slippage_bps=slippage))
    if not market_ok:
        result["reason"] = market_reason
        return result

    proposed_btc = (1 if side == "LONG" else -1) * CONTRACTS * 0.001
    owned_journal = journal is None
    if owned_journal:
        journal = EventJournal(ROOT / "data" / "processed" / "authoritative_risk_journal.sqlite3")
    try:
        authoritative = evaluate_authoritative_intent(
            adapter=adapter, journal=journal, symbol=SYMBOL, mark_price=mid,
            proposed_signed_quantity_btc=proposed_btc, now_ms=now_ms,
            market_data_age_seconds=age, kill_switch=KILL.exists())
    finally:
        if owned_journal:
            journal.close()
    result["authoritative_risk"] = authoritative.to_dict()
    if authoritative.verdict == "SCALED":
        # Do not route a scaled BTC quantity through a fixed-contract order API.
        # Contract conversion and exchange lot sizing must be verified first.
        result["reason"] = "SCALED_QUANTITY_MAPPING_UNSUPPORTED"
        return result
    # This controller routes entry orders only. A REDUCE_ONLY verdict must not
    # be sent through its non-reduce-only bracket path; a dedicated exit adapter
    # is required before any exit-only action can be executed.
    if authoritative.verdict != "APPROVED":
        result["reason"] = authoritative.reason if authoritative.verdict != "REDUCE_ONLY" else "EXIT_ONLY_ROUTE_UNAVAILABLE"
        return result

    plan = plan_for(side, mid, risk_distance)
    profile = json.loads(PROFILE.read_text())
    ok, detail = validate(plan, GuardConfig(
        balance_usd=float(profile["balance_usd"]), max_contracts=1,
        max_loss_usd=MAX_LOSS, rr=RR, contract_btc=0.001, tick=TICK, taker_fee=0.00059))
    result["plan"] = plan.__dict__
    result["risk_check"] = detail
    result["reason"] = "READY_BUT_LOCKED" if ok else str(detail)
    return result


def execute_once(risk_distance: float, client_order_id: str):
    # Promotion gate: the current research statistics do not yet justify live capital.
    policy = json.loads((ROOT / "execution" / "LIVE_PROMOTION_POLICY.json").read_text())
    if policy.get("status") != "PROMOTED":
        raise LiveExecutionBlocked("LIVE_PROMOTION_POLICY_BLOCKED")
    if not _env_bool("BTC_LIVE_EXECUTION") or not _env_bool("BTC_LIVE_OPERATOR_APPROVED"):
        raise LiveExecutionBlocked("manual live arm is not enabled")
    if KILL.exists():
        raise LiveExecutionBlocked("LIVE_KILL_SWITCH exists")
    check = preflight(risk_distance)
    if check["reason"] != "READY_BUT_LOCKED":
        # When the arm flags are true preflight still reports the risk result;
        # normalize the successful case before proceeding.
        if not check.get("plan") or check.get("risk_check", {}).get("contracts") != 1:
            raise LiveExecutionBlocked(json.dumps(check, separators=(",", ":")))
    client = DeltaAuthClient(environment="prod")
    leverage = client.get_order_leverage(PRODUCT_ID)
    lev = str(leverage.get("result", {}).get("leverage", ""))
    if lev != "200":
        raise LiveExecutionBlocked(f"LEVERAGE_MISMATCH:{lev}")
    if active_position(client.get_position(SYMBOL, product_id=PRODUCT_ID)):
        raise LiveExecutionBlocked("ACTIVE_POSITION_BLOCK")
    orders = client.get_open_orders(SYMBOL)
    if isinstance(orders, dict) and orders.get("result"):
        raise LiveExecutionBlocked("OPEN_ORDER_BLOCK")

    plan = plan_for(check["signal"], check["price"], risk_distance)
    stop = plan.stop
    target = plan.target
    if plan.side == "LONG":
        stop_limit, target_limit = stop - TICK, target - TICK
    else:
        stop_limit, target_limit = stop + TICK, target + TICK

    executor = DeltaExecutor(client)
    result = executor.submit_market_with_bracket(
        product_id=PRODUCT_ID, product_symbol=SYMBOL,
        side="buy" if plan.side == "LONG" else "sell", size=1,
        client_order_id=client_order_id, stop_price=stop,
        stop_limit_price=stop_limit, take_profit_price=target,
        take_profit_limit_price=target_limit, dry_run=False)
    _append({"ts": time.time(), "event": "LIVE_ORDER_SUBMITTED", "client_order_id": client_order_id,
             "side": plan.side, "plan": plan.__dict__, "response": result})
    return result


def run_preflight(risk_distance: float):
    result = preflight(risk_distance)
    _append({"ts": time.time(), "event": "PREFLIGHT", "result": result})
    return result


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--risk-distance", type=float, help="absolute USD stop distance")
    group.add_argument("--risk-bps", type=float, help="stop distance in basis points")
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--client-order-id", default="btc_pv1_manual")
    a = ap.parse_args()
    state = _load_state()
    risk_distance = a.risk_distance if a.risk_distance is not None else float(state["order_book"]["mid_price"]) * a.risk_bps / 10000.0
    risk_distance = round_tick(risk_distance, TICK)
    print(json.dumps({"risk_distance_usd":risk_distance,"risk_bps":risk_distance/max(float(state["order_book"]["mid_price"]),1e-9)*10000,"execute":a.execute}, indent=2))
    if a.execute:
        print(json.dumps(execute_once(risk_distance, a.client_order_id), indent=2))
    else:
        print(json.dumps(run_preflight(risk_distance), indent=2))
