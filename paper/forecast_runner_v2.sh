#!/data/data/com.termux/files/usr/bin/bash
cd /data/data/com.termux/files/home/btc_fisher_trader
while true; do
  python3 paper/forecast_journal_v2.py
  sleep 10
done
