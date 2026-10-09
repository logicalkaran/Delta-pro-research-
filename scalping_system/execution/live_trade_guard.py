"""Hard safety gate for BTCUSD live execution.
This module NEVER submits orders. It validates a proposed trade plan.
"""
from dataclasses import dataclass

@dataclass(frozen=True)
class TradePlan:
    side: str
    entry: float
    stop: float
    target: float
    contracts: int = 1

@dataclass(frozen=True)
class GuardConfig:
    balance_usd: float = 2.50
    max_contracts: int = 1
    max_loss_usd: float = 0.35
    rr: float = 2.0
    contract_btc: float = 0.001
    tick: float = 0.5
    # 0.05% BTCUSD taker fee plus 18% GST on the trading fee = 0.059%.
    taker_fee: float = 0.00059

def round_tick(p: float, tick: float = 0.5) -> float:
    return round(p / tick) * tick

def validate(plan: TradePlan, cfg: GuardConfig = GuardConfig()):
    if plan.side not in ("LONG","SHORT"):
        return False, "SIDE_BLOCK"
    if plan.contracts < 1 or plan.contracts > cfg.max_contracts:
        return False, "CONTRACT_LIMIT"
    if plan.entry <= 0 or plan.stop <= 0 or plan.target <= 0:
        return False, "PRICE_BLOCK"
    if plan.side == "LONG" and not (plan.stop < plan.entry < plan.target):
        return False, "LEVEL_ORDER"
    if plan.side == "SHORT" and not (plan.target < plan.entry < plan.stop):
        return False, "LEVEL_ORDER"

    risk_move = abs(plan.entry - plan.stop)
    reward_move = abs(plan.target - plan.entry)
    if risk_move <= 0:
        return False, "ZERO_RISK"
    rr = reward_move / risk_move
    if rr < cfg.rr:
        return False, "RR_BLOCK"

    gross_loss = risk_move * cfg.contract_btc * plan.contracts
    gross_reward = reward_move * cfg.contract_btc * plan.contracts
    entry_fee = plan.entry * cfg.contract_btc * plan.contracts * cfg.taker_fee
    stop_fee = plan.stop * cfg.contract_btc * plan.contracts * cfg.taker_fee
    target_fee = plan.target * cfg.contract_btc * plan.contracts * cfg.taker_fee
    net_loss = gross_loss + entry_fee + stop_fee
    net_reward = gross_reward - entry_fee - target_fee

    if net_loss > cfg.max_loss_usd:
        return False, f"LOSS_BLOCK:{net_loss:.4f}"
    if net_reward <= 0:
        return False, "NET_REWARD_BLOCK"

    return True, {
        "rr_price": rr,
        "gross_loss_usd": gross_loss,
        "gross_reward_usd": gross_reward,
        "estimated_loss_with_taker_fees_usd": net_loss,
        "estimated_reward_after_taker_fees_usd": net_reward,
        "contracts": plan.contracts,
    }
