#!/data/data/com.termux/files/usr/bin/bash
set -eu
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
for f in data/run/collector.pid data/run/dashboard.pid; do
  if [ -f "$f" ]; then
    pid="$(cat "$f")"
    kill "$pid" 2>/dev/null || true
    rm -f "$f"
  fi
done
echo "Paper platform stopped."
