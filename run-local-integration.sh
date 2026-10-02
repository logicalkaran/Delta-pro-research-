#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
BTC_DIR="${BTC_FISHER_TRADER_DIR:-$HOME/btc_fisher_trader}"

if [ ! -f "$BTC_DIR/integration_api.py" ]; then
  echo "BTC bridge not found: $BTC_DIR/integration_api.py" >&2
  echo "Set BTC_FISHER_TRADER_DIR to your existing btc_fisher_trader directory." >&2
  exit 1
fi
if [ ! -f "$APP_DIR/package.json" ]; then
  echo "DeltaPro package.json not found in $APP_DIR" >&2
  exit 1
fi
if [ ! -x "$APP_DIR/node_modules/.bin/tsx" ]; then
  echo "Dependencies are not installed. Install them separately after reviewing package.json." >&2
  exit 1
fi

# One ephemeral random token is shared only by these local processes.
export BTC_DELTA_BRIDGE_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
export BTC_DELTA_BRIDGE_URL="http://127.0.0.1:8788"
export BTC_DELTA_BRIDGE_PORT=8788

python3 "$BTC_DIR/integration_api.py" &
BRIDGE_PID=$!
cleanup() {
  kill "$BRIDGE_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

sleep 1
cd "$APP_DIR"
npm run dev
