import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from paper.live_execution_paper_v3 import build_trade, ALLOW_LOW_VOLATILITY, MAX_TARGET_ATR
from strategy.predictive_levels_v1 import Level, PredictiveLevels

def levels(price, atr, support, resistance, regime="NORMAL_VOLATILITY"):
    return PredictiveLevels(
        price=price, atr=atr, atr_pct=atr/price*100,
        support=(Level(support,"SUPPORT",80,((support/price)-1)*10000,("TEST",)),),
        resistance=(Level(resistance,"RESISTANCE",80,((resistance/price)-1)*10000,("TEST",)),),
        nearest_support=support, nearest_resistance=resistance,
        value_low=support, poc=price, value_high=resistance, regime=regime
    )

def test_remote_target_is_rejected_when_near_level_is_too_close():
    # Entry 100, stop 98, nearest resistance 101 is < 1.5R.
    assert build_trade("LONG", 100.0, levels(100, 4, 98, 101)) is None

def test_nearest_structural_target_is_used_when_it_meets_rr():
    plan = build_trade("LONG", 100.0, levels(100, 4, 98, 105))
    assert plan is not None
    assert plan["target"] == 105.0
    assert plan["rr"] >= 1.5
    assert plan["target"] - plan["entry"] <= MAX_TARGET_ATR * plan["atr"]

def test_short_target_uses_nearest_support():
    plan = build_trade("SHORT", 100.0, levels(100, 4, 95, 102))
    assert plan is not None
    assert plan["target"] == 95.0

def test_low_volatility_is_not_enabled_by_default():
    assert ALLOW_LOW_VOLATILITY is False
