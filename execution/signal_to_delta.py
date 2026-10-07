"""Risk-gated Delta execution bridge.

The default mode is dry-run and therefore safe to call from signal workflows.
It converts the existing RiskEngine's BTC quantity into Delta integer contracts.
"""
from __future__ import annotations
from execution.delta_client_private import DeltaAuthClient
from execution.delta_executor import DeltaExecutor
from execution.delta_product import load_product, validate_market_order
from risk.limits import RiskEngine

def prepare_order(*, decision: str, mark_price: float, usd_inr: float,
                  notional_inr: float = 5000.0, current_positions: int = 0,
                  daily_loss_inr: float = 0.0, kill_switch_active: bool = False,
                  client_order_id: str = "BTC-FISHER-DRYRUN"):
    if decision not in {"LONG", "SHORT"}:
        return {"allowed": False, "reason": "decision_not_tradeable"}

    product = load_product("BTCUSD")
    risk = RiskEngine(
        live_trading=False, max_positions=1,
        max_position_notional_inr=notional_inr,
        max_daily_loss_inr=250, max_order_notional_inr=notional_inr,
        kill_switch=True, contract_value_btc=product.contract_value_btc,
    )
    rd = risk.check(
        order_notional_inr=notional_inr,
        current_positions=current_positions,
        daily_loss_inr=daily_loss_inr,
        btc_usd_price=mark_price,
        usd_inr=usd_inr,
        kill_switch_active=kill_switch_active,
    )
    if not rd.allowed or rd.position_size is None:
        return {"allowed": False, "reason": rd.reason}

    contracts = rd.position_size.contracts
    side = "buy" if decision == "LONG" else "sell"
    validate_market_order(product, contracts, side)

    payload = DeltaExecutor().submit_market(
        product_id=product.product_id,
        product_symbol=product.symbol,
        side=side,
        size=contracts,
        client_order_id=client_order_id,
        dry_run=True,
    )
    return {
        "allowed": True,
        "reason": rd.reason,
        "contracts": contracts,
        "quantity_btc": rd.position_size.quantity_btc,
        "inr_notional": rd.position_size.inr_notional,
        "payload": payload["payload"],
    }
