#!/data/data/com.termux/files/usr/bin/bash
# Low-frequency quality gate; never submits orders or auto-edits production code.
set -u
ROOT="$HOME/btc_fisher_trader"
PY="$ROOT/.venv/bin/python"
LOG="$ROOT/logs/edge_node_healthcheck.log"
REPORT="$ROOT/logs/edge_node_ai_diagnosis.md"
mkdir -p "$ROOT/logs"
cd "$ROOT" || exit 2

{
  printf '\n[%s] EDGE_NODE_CHECK_START\n' "$(date -Iseconds)"
  if [ ! -x "$PY" ]; then
    echo "BLOCKED: project virtualenv python is missing"
    exit 2
  fi

  "$PY" -m pytest -q \
    risk/test_orchestration_oracle.py \
    risk/test_orchestration_watchdog.py \
    risk/test_hedge_coordinator.py \
    risk/test_concurrent_risk_gate.py \
    risk/test_production_guard.py \
    execution/test_twap_ledger.py \
    execution/test_emergency_sequence.py \
    execution/test_paper_simulator.py \
    execution/test_authoritative_account_risk.py \
    execution/test_live_perpetual_controller_authoritative.py \
    exchange/test_delta_state_adapter.py \
    recovery/test_state_reconciler.py \
    execution/test_adaptive_pacing.py \
    execution/test_live_execution_gate.py \
    execution/test_production_audit.py \
    storage
  TEST_STATUS=$?
  if [ "$TEST_STATUS" -eq 0 ]; then
    echo "QUALITY_GATE=PASS"
    echo "No AI review needed; keeping CPU/network usage low."
    exit 0
  fi

  echo "QUALITY_GATE=FAIL status=$TEST_STATUS"
  echo "Requesting read-only Codex diagnosis; no automatic code changes."
  if command -v codex >/dev/null 2>&1; then
    PROMPT='Review failed tests and orchestration/risk/hedge/TWAP/emergency/event-journal/adaptive-pacing modules. Do not edit files, run exchange calls, or change live trading configuration. Return diagnosis, exact files/lines, and a proposed unified diff. Do not recommend enabling live execution. Preserve pre-existing uncommitted changes.'
    printf '%s\n' "$PROMPT" | codex exec --sandbox read-only --cd "$ROOT" - > "$REPORT" 2>&1
    AI_STATUS=$?
    echo "CODEX_DIAGNOSIS_STATUS=$AI_STATUS report=$REPORT"
  else
    echo "CODEX_UNAVAILABLE: inspect failed tests manually"
  fi
  echo "ACTION_REQUIRED: inspect diagnosis and approve any patch manually."
  exit "$TEST_STATUS"
} >> "$LOG" 2>&1
