#!/data/data/com.termux/files/usr/bin/sh
# Lightweight watchdog: restart crond if it exits. No trading or API access.
PATH="/data/data/com.termux/files/usr/bin:/system/bin:/system/xbin"
export PATH
LOG="/data/data/com.termux/files/home/ai-node/scheduled_logs/boot.log"
LOCK="/data/data/com.termux/files/home/.cache/btc-fisher-cron-watchdog"
mkdir -p "$(dirname "$LOG")" "$(dirname "$LOCK")"
if ! mkdir "$LOCK" 2>/dev/null; then
    oldpid="$(cat "$LOCK/pid" 2>/dev/null || true)"
    if [ -n "$oldpid" ] && kill -0 "$oldpid" 2>/dev/null; then exit 0; fi
    rm -rf "$LOCK"
    mkdir "$LOCK" 2>/dev/null || exit 0
fi
echo "$$" > "$LOCK/pid"
trap 'rm -rf "$LOCK"' EXIT INT TERM
echo "$(date -Is) | cron watchdog started" >> "$LOG"
while :; do
    # Termux pgrep -x is unreliable on this device; match the daemon's exact command path.
    if ! pgrep -f '^/data/data/com.termux/files/usr/bin/crond([[:space:]]|$)' >/dev/null 2>&1; then
        /data/data/com.termux/files/usr/bin/crond
        sleep 1
        if pgrep -f '^/data/data/com.termux/files/usr/bin/crond([[:space:]]|$)' >/dev/null 2>&1; then
            echo "$(date -Is) | WATCHDOG successfully started crond" >> "$LOG"
        else
            echo "$(date -Is) | ERROR: crond start failed" >> "$LOG"
        fi
        if command -v termux-notification >/dev/null 2>&1; then
            termux-notification --title "BTC paper monitor" --content "Cron daemon recovery attempt; check boot log" --id btc-paper-watchdog >/dev/null 2>&1 || true
        fi
    fi
    sleep 60
done
