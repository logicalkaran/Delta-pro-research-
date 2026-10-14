# Autonomous Research Node v1

This is a bounded, paper-only supervisor for the existing Delta BTCUSD research stack. It runs the existing public websocket feed, live-market paper simulator, predefined hypothesis registry, causal prediction diagnostics, and a deterministic evidence report.

## Run

```sh
cd ~/btc_fisher_trader
python research/autonomous_research_node_v1.py --seconds 180
```

Use `--no-paper` to observe the public feed and run offline diagnostics without starting the paper simulator. The session is bounded to 1–86400 seconds. Termux is not a guaranteed persistent host; use an external always-on host for genuine 24/7 operation.

## Outputs

- `data/processed/autonomous_research_node_v1.json` — latest session report
- `data/processed/autonomous_research_node_v1.jsonl` — session health/event journal
- `data/processed/prediction_hypothesis_registry_v1.json` — predeclared hypotheses and falsifiers
- `data/processed/prediction_layer_v1.json` — causal feature and walk-forward diagnostics
- `data/processed/live_execution_paper_v3_summary.json` — simulated execution results

## Safety and interpretation

- Public market data only; no private API or exchange order endpoint is invoked.
- Real order submission remains disabled. The promotion policy remains `BLOCKED_UNTIL_VALIDATED`.
- Missing/stale market state or an existing kill switch causes fail-closed behavior.
- The node does not execute LLM-generated source code, alter the frozen MonthlyFisher strategy, alter risk limits, or automatically promote a model.
- A short run is an integration/health check, not profitability evidence. Zero trades means zero measured edge, not a successful strategy.
- Paper fills, costs, and feed conditions are approximations; validate fees, funding, queue position, slippage, and walk-forward robustness before any human-reviewed promotion decision.
- LLM providers (local Qwen / Gemini CLI) are not invoked by this supervisor yet. Their eventual role must be advisory hypothesis drafting; deterministic tests and independent evaluation decide whether a hypothesis survives.
