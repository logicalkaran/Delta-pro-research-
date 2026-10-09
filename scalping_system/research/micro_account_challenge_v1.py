"""Realistic $2 micro-account paper challenge.

Research/simulation only. Never submits exchange orders.
Models account equity, risk-per-trade, leverage cap, fees, slippage,
adverse selection, minimum contract size and compounding.
"""
from dataclasses import dataclass
from math import floor

@dataclass(frozen=True)
class ChallengeConfig:
    starting_usd: float=2.0
    target_usd: float=4.0
    risk_fraction: float=0.10
    max_risk_fraction: float=0.15
    leverage_cap: float=3.0
    fee_bps_roundtrip: float=11.0
    slippage_bps_roundtrip: float=4.0
    adverse_bps_roundtrip: float=3.0
    min_contract_btc: float=0.001
    max_consecutive_losses: int=2
    min_rr: float=2.5

@dataclass(frozen=True)
class ChallengeResult:
    allowed: bool
    reason: str
    equity: float
    risk_usd: float
    notional_usd: float
    contracts: int

def size(equity, btc_price_usd, stop_distance_pct, cfg=ChallengeConfig()):
    if equity<=0: return ChallengeResult(False,"ACCOUNT_DEPLETED",equity,0,0,0)
    if equity>=cfg.target_usd: return ChallengeResult(False,"TARGET_REACHED",equity,0,0,0)
    if stop_distance_pct<=0: return ChallengeResult(False,"INVALID_STOP_DISTANCE",equity,0,0,0)
    if stop_distance_pct>0.05: return ChallengeResult(False,"STOP_TOO_WIDE_FOR_MICRO_ACCOUNT",equity,0,0,0)
    risk_pct=min(cfg.risk_fraction,cfg.max_risk_fraction)
    risk=equity*risk_pct
    notional=risk/(stop_distance_pct)
    max_notional=equity*cfg.leverage_cap
    notional=min(notional,max_notional)
    contract_usd=cfg.min_contract_btc*btc_price_usd
    contracts=floor(notional/contract_usd)
    actual_notional=contracts*contract_usd
    if contracts<1: return ChallengeResult(False,"MINIMUM_CONTRACT_OR_NOTIONAL_CONSTRAINT",equity,risk,0,0)
    return ChallengeResult(True,"SIZE_ALLOWED",equity,risk,actual_notional,contracts)

def settle(equity, entry, exit_price, contracts, side, cfg=ChallengeConfig()):
    qty=contracts*cfg.min_contract_btc
    gross=(exit_price-entry)*qty if side=="LONG" else (entry-exit_price)*qty
    cost=(entry+exit_price)*qty*(cfg.fee_bps_roundtrip+cfg.slippage_bps_roundtrip+cfg.adverse_bps_roundtrip)/20000
    return equity+gross-cost

if __name__=="__main__":
    c=ChallengeConfig()
    print({"starting_usd":c.starting_usd,"target_usd":c.target_usd,
           "risk_fraction":c.risk_fraction,"leverage_cap":c.leverage_cap,
           "min_contract_btc":c.min_contract_btc,"min_rr":c.min_rr,
           "paper_only":True})
