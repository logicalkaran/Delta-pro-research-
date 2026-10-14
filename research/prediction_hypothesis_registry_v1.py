"""Prediction hypothesis tournament v1. Research/paper only.

Generates testable hypotheses without changing execution, leverage, risk, or production strategy.
Each hypothesis must specify:
- causal intuition
- measurable features
- falsification criteria
- validation design
- expected failure mode
"""
from pathlib import Path
import json,time

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data/processed/prediction_hypothesis_registry_v1.json"

HYPOTHESES=[
 {
  "id":"FLOW_PRICE_CONFIRMATION",
  "thesis":"Aggressive flow should predict short-horizon continuation only when price actually responds in the same direction.",
  "features":["delta5","delta30","imbalance_5","return1","return3","return5","atr_pct","spread_bps"],
  "entry_condition":"flow direction agrees with price response and spread/cost is acceptable",
  "falsifier":"walk-forward net expectancy <= 0 or no improvement versus flow-only baseline",
  "horizons":[1,2,3,5]
 },
 {
  "id":"ABSORPTION_FAILURE",
  "thesis":"Apparent absorption is useful only when aggressive flow fails to move price and the subsequent reversal confirms.",
  "features":["delta5","delta30","return1","return3","return5","imbalance_5","distance_to_level_bps","atr_pct"],
  "entry_condition":"extreme aggressive flow + weak price response + reversal confirmation near structural liquidity",
  "falsifier":"reversal confirmation does not improve out-of-sample net expectancy",
  "horizons":[1,2,3,5]
 },
 {
  "id":"LIQUIDITY_SWEEP_RECLAIM",
  "thesis":"A sweep beyond a recent structural level followed by fast reclaim may predict mean reversion better than raw imbalance.",
  "features":["sweep_distance_bps","reclaim_speed_s","return1","return3","delta5","imbalance_5","level_strength","atr_pct"],
  "entry_condition":"level sweep + reclaim + flow divergence",
  "falsifier":"no positive improvement after fees/slippage in both validation halves",
  "horizons":[1,2,3,5]
 },
 {
  "id":"REGIME_CONDITIONAL_FLOW",
  "thesis":"The same flow signal may have opposite predictive value across volatility/trend regimes.",
  "features":["delta5","delta30","imbalance_5","atr_pct","trend_strength","volume_ratio","regime"],
  "entry_condition":"signal is enabled only in empirically positive regimes",
  "falsifier":"regime-conditioned result fails stability or collapses in later walk-forward folds",
  "horizons":[1,2,3,5]
 },
 {
  "id":"FLOW_DIVERGENCE",
  "thesis":"When aggressive flow and price disagree strongly, the disagreement may contain reversal information.",
  "features":["delta5","delta30","return1","return3","return5","imbalance_5","atr_pct","spread_bps"],
  "entry_condition":"large flow/price divergence followed by stabilization",
  "falsifier":"divergence does not beat matched directional-flow controls",
  "horizons":[1,2,3,5]
 },
 {
  "id":"ORDERBOOK_PERSISTENCE",
  "thesis":"Persistent imbalance may be more predictive than a single orderbook snapshot.",
  "features":["imbalance_5","imbalance_5_lag1","imbalance_5_lag2","imbalance_duration_s","delta5","return3"],
  "entry_condition":"imbalance persists across multiple observations and price confirms",
  "falsifier":"persistence adds no incremental out-of-sample information",
  "horizons":[1,2,3,5]
 }
]

def main():
    out={
      "updated_at":time.time(),
      "status":"RESEARCH_ONLY",
      "hypotheses":HYPOTHESES,
      "ranking_rule":{
        "primary":"out_of_sample_net_expectancy_after_costs",
        "secondary":["profit_factor","positive_both_halves","drawdown","sample_count"],
        "minimum_independent_samples":100,
        "minimum_profit_factor":1.2,
        "require_positive_both_halves":True,
        "no_win_rate_only_optimization":True
      },
      "execution_policy":{
        "leverage_changed":False,
        "risk_changed":False,
        "production_strategy_changed":False,
        "real_orders":False,
        "automatic_promotion":False
      }
    }
    OUT.write_text(json.dumps(out,indent=2))
    print(json.dumps({"hypotheses":len(HYPOTHESES),"output":str(OUT),"policy":out["execution_policy"]},indent=2))

if __name__=="__main__":main()
