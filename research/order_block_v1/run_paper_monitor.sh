#!/data/data/com.termux/files/usr/bin/sh
set -eu
PATH="/data/data/com.termux/files/usr/bin:/system/bin:/system/xbin"
export PATH
ROOT="/data/data/com.termux/files/home/btc_fisher_trader/research/order_block_v1"
OUT="$ROOT/output/paper_monitor"
mkdir -p "$OUT"
exec 9>"$OUT/monitor.lock"
if ! flock -n 9; then
  printf '%s | skipped: previous monitor run still active\n' "$(date -Is)" >> "$OUT/monitor.log"
  exit 0
fi
cd "$ROOT/../.."
PY="/data/data/com.termux/files/usr/bin/python"
if [ ! -x "$PY" ]; then PY="/data/data/com.termux/files/usr/bin/python3"; fi
if [ ! -x "$PY" ]; then echo "Python executable missing" >&2; exit 127; fi
printf '%s | monitor run started\n' "$(date -Is)" >> "$OUT/monitor.log"
if "$PY" "$ROOT/paper_monitor.py" >> "$OUT/monitor.log" 2>&1; then
  printf '%s | monitor run completed\n' "$(date -Is)" >> "$OUT/monitor.log"
else
  rc=$?
  printf '%s | monitor run failed rc=%s\n' "$(date -Is)" "$rc" >> "$OUT/monitor.log"
  if command -v termux-notification >/dev/null 2>&1; then
    termux-notification --title "BTC paper monitor FAILED" --content "Monitor failed (exit $rc). Check research/order_block_v1/output/paper_monitor/monitor.log" --id btc-paper-monitor-error >/dev/null 2>&1 || true
  fi
  exit "$rc"
fi
