"""Final pre-trade readiness checker. Read-only; never submits orders."""
import json, os, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
state=json.loads((ROOT/"data/live_microstructure_state.json").read_text())
print("=== BTCUSD LIVE READINESS ===")
print("timestamp:", time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()))
print("balance_reference_usd: 2.50")
print("live_order_submission: DISABLED")
print("max_contracts: 1")
print("rr_minimum: 1:2")
print("")

w5=state["windows"]["5"]; w30=state["windows"]["30"]
ob=state["order_book"]; q=state["quality"]
print("price:", ob["mid_price"])
print("5s delta:", w5["delta_pct"], "trades:", w5["trades"])
print("30s delta:", w30["delta_pct"], "trades:", w30["trades"])
print("5s momentum:", state["price"]["5"]["return_pct"])
print("L2 imbalance:", ob["imbalance_5"])
print("spread:", ob["spread"])
print("fresh:", q["fresh_seconds"])

# V3 requires 4 trades, aligned 5s/30s delta, imbalance and >=0.025% 5s momentum.
long_ok = (
    w5["trades"] >= 4 and w5["delta_pct"] >= .12 and
    w30["delta_pct"] >= .08 and ob["imbalance_5"] >= .12 and
    state["price"]["5"]["return_pct"] >= .025 and
    q["fresh_seconds"] <= 2
)
short_ok = (
    w5["trades"] >= 4 and w5["delta_pct"] <= -.12 and
    w30["delta_pct"] <= -.08 and ob["imbalance_5"] <= -.12 and
    state["price"]["5"]["return_pct"] <= -.025 and
    q["fresh_seconds"] <= 2
)
print("V3 LONG:", "PASS" if long_ok else "BLOCK")
print("V3 SHORT:", "PASS" if short_ok else "BLOCK")
print("FINAL:", "WAIT — NO VALID SIGNAL" if not (long_ok or short_ok) else "SIGNAL DETECTED — RISK GATE REQUIRED")
