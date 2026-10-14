#!/usr/bin/env python3
"""One-shot, read-only BTCUSD 15m order-block paper monitor. Never places orders."""
import json, hashlib, sys, time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUT = HERE / "output" / "paper_monitor"
sys.path.insert(0, str(HERE))
import order_block_experiment as ob

THRESHOLD_BPS = 60.0
FEE_BPS = 5.0
SLIPPAGE_BPS = 2.0
FETCH_DAYS = 7

def utc(ts):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()

def key_for(trade):
    return "|".join((trade.side, str(trade.signal_at), str(trade.entry_at)))

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    source = HERE / "btcusd_15m.csv"
    historical = ob.read_csv(source)
    cutoff = max(c.timestamp for c in historical)
    now_epoch = int(time.time())
    # Ignore the currently forming 15m candle; only completed bars are eligible.
    fetched = [c for c in ob.fetch_history(days=FETCH_DAYS, symbol="BTCUSD")
               if c.timestamp > cutoff and c.timestamp + 900 <= now_epoch]
    if not fetched:
        raise SystemExit("No completed fresh candles after historical cutoff; no ledger events written.")
    collected_path = OUT / "collected_fresh_candles.csv"
    previously_collected = ob.read_csv(collected_path) if collected_path.exists() else []
    fresh = ob.validate_candles(previously_collected + fetched)
    if not fresh:
        raise SystemExit("Persistent fresh candle history is empty; no ledger events written.")
    candles = ob.validate_candles(historical + fresh)
    ob.write_csv(OUT / "latest_fresh_candles.csv", fetched)
    ob.write_csv(collected_path, fresh)
    raw = ob.simulate(candles, fee_bps_per_side=FEE_BPS,
                      slippage_bps_per_side=SLIPPAGE_BPS, min_risk_bps=0.0)
    filtered = ob.simulate(candles, fee_bps_per_side=FEE_BPS,
                           slippage_bps_per_side=SLIPPAGE_BPS,
                           min_risk_bps=THRESHOLD_BPS)
    raw_new = [t for t in raw if t.entry_at > cutoff and t.exit_at <= max(c.timestamp for c in candles)]
    filtered_new = [t for t in filtered if t.entry_at > cutoff and t.exit_at <= max(c.timestamp for c in candles)]
    accepted = {key_for(t): t for t in filtered_new}
    candidates = {key_for(t): t for t in raw_new}
    ledger = OUT / "events.jsonl"
    seen = set()
    if ledger.exists():
        for line in ledger.read_text(encoding="utf-8").splitlines():
            try:
                item = json.loads(line)
                if item.get("event_key"):
                    seen.add(item["event_key"])
            except json.JSONDecodeError:
                raise SystemExit("Ledger contains malformed JSON; refusing to append.")
    now = datetime.now(timezone.utc).isoformat()
    events = []
    for key, t in candidates.items():
        if key in seen:
            continue
        risk_bps = abs(t.entry - t.stop) / t.entry * 10000
        accepted_trade = key in accepted
        events.append({
            "event_key": key, "observed_at_utc": now,
            "event_type": "PAPER_ACCEPTED" if accepted_trade and risk_bps >= THRESHOLD_BPS else "FILTER_REJECTED",
            "reason": "risk_width_meets_fixed_threshold" if accepted_trade and risk_bps >= THRESHOLD_BPS else "risk_width_below_fixed_threshold",
            "side": t.side, "signal_at_utc": utc(t.signal_at), "entry_at_utc": utc(t.entry_at),
            "exit_at_utc": utc(t.exit_at), "entry": t.entry, "stop": t.stop, "target": t.target,
            "exit": t.exit, "risk_width_bps": round(risk_bps, 4), "gross_r": t.gross_r,
            "estimated_net_r": t.net_r, "exit_reason": t.exit_reason, "bars_held": t.bars_held,
            "fee_bps_per_side_assumed": FEE_BPS, "slippage_bps_per_side_assumed": SLIPPAGE_BPS,
            "threshold_bps_fixed": THRESHOLD_BPS, "live_execution_enabled": False
        })
    with ledger.open("a", encoding="utf-8") as f:
        for event in events:
            f.write(json.dumps(event, separators=(",", ":")) + "\n")
        heartbeat = {
            "event_key": "heartbeat|" + now, "event_type": "MONITOR_RUN",
            "observed_at_utc": now, "historical_cutoff_utc": utc(cutoff),
            "fetched_completed_candles": len(fetched), "cumulative_fresh_candles": len(fresh),
            "fetched_first_utc": utc(min(c.timestamp for c in fetched)),
            "fetched_last_utc": utc(max(c.timestamp for c in fetched)),
            "cumulative_first_utc": utc(min(c.timestamp for c in fresh)),
            "cumulative_last_utc": utc(max(c.timestamp for c in fresh)),
            "interval_gaps_combined": sum(b.timestamp-a.timestamp != 900 for a,b in zip(candles,candles[1:])),
            "candidate_trades_seen": len(raw_new), "filtered_trades_seen": len(filtered_new),
            "new_events_appended": len(events), "fixed_threshold_bps": THRESHOLD_BPS,
            "fee_bps_per_side_assumed": FEE_BPS, "slippage_bps_per_side_assumed": SLIPPAGE_BPS,
            "historical_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "live_execution_enabled": False
        }
        f.write(json.dumps(heartbeat, separators=(",", ":")) + "\n")
    print(json.dumps({"status":"PASS","ledger":str(ledger),"fresh_candles":len(fresh),
        "new_candidate_trades":len(raw_new),"new_filtered_trades":len(filtered_new),
        "new_events_appended":len(events),"heartbeat":heartbeat,
        "live_execution_enabled":False}, indent=2))

if __name__ == "__main__":
    main()
