#!/data/data/com.termux/files/usr/bin/bash
set -eu
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
mkdir -p data/run logs

is_running() {
  [ -f "$1" ] && kill -0 "$(cat "$1")" 2>/dev/null
}

stop_duplicate_collectors() {
  pids="$(ps -A -o pid,args | awk '/python -m delta_collector.websocket_client_v2/ && !/awk/ {print $1}')"
  count="$(printf '%s\n' "$pids" | awk 'NF{n++} END{print n+0}')"
  if [ "$count" -gt 1 ]; then
    keep="$(printf '%s\n' "$pids" | head -n 1)"
    printf '%s\n' "$pids" | while read -r pid; do
      [ -z "$pid" ] && continue
      [ "$pid" = "$keep" ] || kill "$pid" 2>/dev/null || true
    done
  fi
}

start_one() {
  name="$1"; pidfile="$2"; logfile="$3"; shift 3
  if is_running "$pidfile"; then
    echo "$name already running (PID $(cat "$pidfile"))"
    return
  fi
  nohup "$@" >> "$logfile" 2>&1 &
  pid="$!"
  echo "$pid" > "$pidfile"
  sleep 1
  if ! kill -0 "$pid" 2>/dev/null; then
    rm -f "$pidfile"
    echo "$name failed to start; see $logfile" >&2
    exit 1
  fi
  echo "$name started (PID $pid)"
}

stop_duplicate_collectors
if [ -f data/run/collector.pid ] && ! is_running data/run/collector.pid; then rm -f data/run/collector.pid; fi
if [ -f data/run/dashboard.pid ] && ! is_running data/run/dashboard.pid; then rm -f data/run/dashboard.pid; fi

start_one collector data/run/collector.pid logs/delta_collector.log .venv/bin/python -m delta_collector.websocket_client_v2
start_one dashboard data/run/dashboard.pid logs/dashboard.log .venv/bin/python dashboard_server.py

echo "Paper platform started: http://127.0.0.1:8790"
echo "Readiness: http://127.0.0.1:8790/ready"
echo "Live exchange orders: OFF"
