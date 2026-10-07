"""One-order Delta Demo smoke test."""
from __future__ import annotations
import os, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from execution.delta_client_private import DeltaAuthClient
from execution.delta_executor import DeltaExecutor
from execution.delta_product import load_product, validate_market_order
from execution.delta_reconciler import DeltaReconciler

def run():
    if os.getenv("DELTA_ENV", "demo").lower() != "demo":
        raise RuntimeError("Demo smoke test refuses non-demo environment")
    if os.getenv("DELTA_DEMO_ORDER_TEST", "").lower() != "true":
        raise RuntimeError("Set DELTA_DEMO_ORDER_TEST=true to authorize one Demo order")
    client = DeltaAuthClient(environment="demo")
    product = load_product("BTCUSD", client=None)
    validate_market_order(product, 1, "buy")
    order_id = f"BTC-DEMO-{int(time.time())}"[-32:]
    result = DeltaExecutor(client).submit_market(
        product_id=product.product_id, product_symbol=product.symbol,
        side="buy", size=1, client_order_id=order_id,
        reduce_only=False, dry_run=False,
    )
    print("DEMO ORDER RESPONSE:", result)
    state = DeltaReconciler(client).reconcile("BTCUSD")
    found = DeltaReconciler(client).find_client_order(state.orders, order_id)
    print("RECONCILED ORDER:", found)
    print("RECONCILED POSITION:", state.position)
    if found is None:
        raise RuntimeError("Order response could not be reconciled from Delta")
    print("Delta Demo order + reconciliation: PASS")

if __name__ == "__main__":
    run()
