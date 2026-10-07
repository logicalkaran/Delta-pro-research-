#!/data/data/com.termux/files/usr/bin/bash
set -u
cd "$(dirname "$0")/.."
while true; do
  python3 research/live_paper_leaderboard_v1.py > data/processed/live_paper_leaderboard_latest.json.tmp 2>&1 || true
  mv data/processed/live_paper_leaderboard_latest.json.tmp data/processed/live_paper_leaderboard_latest.log 2>/dev/null || true
  python3 research/scalper_regime_session_v1.py > data/processed/scalper_regime_session_latest.log 2>&1 || true
  sleep 60
done
