"""Finite offline event-driven sampler for recorded Delta BTC messages. Research only."""
import argparse
import json
import math
import statistics
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "data/raw/delta_btc_raw.jsonl"
DEFAULT_OUTPUT = ROOT / "data/processed/event_driven_capture_observer_v1.json"
COOLDOWN_SECONDS = 0.250
BASELINE_SECONDS = 1.0


def normalize_epoch(value):
    """Return (seconds, classification), detecting epoch s/ms/us/ns by magnitude."""
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None, "invalid"
    if not math.isfinite(x) or x <= 0:
        return None, "invalid"
    if x >= 1e17:
        return x / 1e9, "nanoseconds"
    if x >= 1e14:
        return x / 1e6, "microseconds"
    if x >= 1e11:
        return x / 1e3, "milliseconds"
    return x, "seconds"


def parse_receive(value):
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except (ValueError, OverflowError):
        return None


def quote_from(message):
    try:
        bid, ask = float(message["bp"]), float(message["ap"])
    except (KeyError, TypeError, ValueError):
        return None, "missing_or_non_numeric_bid_ask"
    if not math.isfinite(bid) or not math.isfinite(ask) or bid <= 0 or ask <= 0:
        return None, "nonpositive_or_nonfinite_quote"
    if ask < bid:
        return None, "crossed_quote"
    return {"bid": bid, "ask": ask, "mid": (bid + ask) / 2,
            "spread": ask - bid, "spread_bps": (ask - bid) / ((ask + bid) / 2) * 10000}, None


def gaps_summary(gaps):
    if not gaps:
        return {"count": 0, "median_seconds": None, "p90_seconds": None,
                "p95_seconds": None, "p99_seconds": None, "max_seconds": None,
                "over_1s": 0, "over_2s": 0, "over_5s": 0}
    ordered = sorted(gaps)
    def pct(p):
        return ordered[min(len(ordered)-1, math.ceil(p * len(ordered))-1)]
    return {"count": len(gaps), "median_seconds": statistics.median(ordered),
            "p90_seconds": pct(.90), "p95_seconds": pct(.95), "p99_seconds": pct(.99),
            "max_seconds": max(ordered), "over_1s": sum(x > 1 for x in gaps),
            "over_2s": sum(x > 2 for x in gaps), "over_5s": sum(x > 5 for x in gaps)}


def observe(source):
    source = Path(source)
    stats = Counter()
    missing = Counter()
    timestamp_kinds = Counter()
    samples, valid_receives = [], []
    latest = None
    last_baseline = None
    last_event = None
    previous_quote = None
    with source.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            stats["rows_read"] += 1
            try:
                wrapper = json.loads(line)
            except (json.JSONDecodeError, TypeError):
                stats["malformed_rows"] += 1
                continue
            if not isinstance(wrapper, dict) or not isinstance(wrapper.get("message"), dict):
                stats["malformed_rows"] += 1
                continue
            message = wrapper["message"]
            received = parse_receive(wrapper.get("received_at"))
            if received is None:
                missing["received_at"] += 1
            else:
                valid_receives.append(received)
            channel = message.get("type")
            if channel is None:
                missing["message.type"] += 1
            stats["channel:" + str(channel or "missing")] += 1
            preferred_field = "t" if channel == "trades" else "ts"
            alternate_field = "ts" if preferred_field == "t" else "t"
            ts_field = preferred_field if message.get(preferred_field) is not None else alternate_field
            raw_ts = message.get(ts_field)
            if raw_ts is None:
                missing["message.ts_or_t"] += 1
                event_ts, kind = None, "missing"
            else:
                event_ts, kind = normalize_epoch(raw_ts)
                if kind == "invalid": missing["message." + ts_field] += 1
            timestamp_kinds[kind] += 1
            # Only recognized BTC trade prints are used as triggers; other channel rows are counted.
            is_trade = channel == "trades" and message.get("p") is not None
            if channel not in ("ob_l1", "trades"):
                stats["unknown_rows"] += 1
            quote = None
            if channel == "ob_l1":
                stats["ob_l1_rows"] += 1
                quote, reason = quote_from(message)
                if quote is None:
                    stats["invalid_quotes"] += 1
                    if reason == "crossed_quote": stats["crossed_quotes"] += 1
                    if reason == "missing_or_non_numeric_bid_ask":
                        if "bp" not in message: missing["message.bp"] += 1
                        if "ap" not in message: missing["message.ap"] += 1
                    stats["invalid_quote:" + reason] += 1
                else:
                    stats["valid_quotes"] += 1
                    latest = (quote, event_ts, kind, received, wrapper.get("received_at"), message, line_no)
            if latest is None or received is None:
                continue
            q, ets, ekind, rts, rtext, msg, qline = latest
            reasons = []
            # Baseline cadence is based on local receive timestamps, not exchange timestamps.
            if last_baseline is None or received - last_baseline >= BASELINE_SECONDS:
                reasons.append("periodic_1s")
            event_reasons = []
            if is_trade:
                event_reasons.append("trade_print")
            if previous_quote is not None and channel == "ob_l1" and quote is not None:
                old = previous_quote
                if quote["bid"] != old["bid"] or quote["ask"] != old["ask"]:
                    event_reasons.append("best_quote_change")
                if old["mid"] > 0 and abs(quote["mid"] / old["mid"] - 1) * 10000 >= 1.0:
                    event_reasons.append("mid_move_ge_1bp")
                if abs(quote["spread_bps"] - old["spread_bps"]) >= .5:
                    event_reasons.append("spread_change_ge_0_5bp")
            if channel == "ob_l1" and quote is not None:
                previous_quote = quote
            cooldown_ok = last_event is None or received - last_event >= COOLDOWN_SECONDS
            if event_reasons and cooldown_ok:
                reasons.extend(event_reasons)
                last_event = received
            if not reasons:
                continue
            event_sample = any(x != "periodic_1s" for x in reasons)
            sample = {"line_number": line_no, "event_timestamp": event_ts,
                      "event_timestamp_field": (ts_field if event_ts is not None else None),
                      "event_timestamp_unit": kind, "received_at": wrapper.get("received_at"),
                      "received_timestamp": received, "channel": channel,
                      "message_type": channel,
                      "quote_event_timestamp": ets,
                      "quote_event_timestamp_field": (("ts" if msg.get("ts") is not None else "t") if ets is not None else None),
                      "quote_received_at": rtext,
                      "bid": q["bid"], "ask": q["ask"],
                      "mid": q["mid"], "spread": q["spread"], "spread_bps": q["spread_bps"],
                      "trigger_reasons": reasons,
                      "trade_print": ({"price": message.get("p"), "size": message.get("s"), "role": message.get("r")} if event_sample and is_trade else None)}
            samples.append(sample)
            if "periodic_1s" in reasons:
                stats["periodic_samples"] += 1
                last_baseline = received
            if any(x != "periodic_1s" for x in reasons):
                stats["event_triggered_samples"] += 1
                for reason in event_reasons:
                    if reason in reasons: stats["trigger:" + reason] += 1
            if "periodic_1s" in reasons and event_sample:
                stats["both_periodic_and_event_samples"] += 1
            elif "periodic_1s" in reasons:
                stats["periodic_only_samples"] += 1
            elif event_sample:
                stats["event_only_samples"] += 1
    times = [s["received_timestamp"] for s in samples]
    gaps = [b-a for a,b in zip(times, times[1:]) if b >= a]
    span = (max(valid_receives)-min(valid_receives)) if len(valid_receives) > 1 else 0.0
    return {"research_only": True, "real_orders": False,
            "source_path": str(source), "source_bytes": source.stat().st_size,
            "rows_read": stats["rows_read"], "malformed_rows": stats["malformed_rows"],
            "unknown_rows": stats["unknown_rows"], "channel_counts": {k[8:]: v for k,v in stats.items() if k.startswith("channel:")},
            "ob_l1_rows": stats["ob_l1_rows"], "valid_quotes": stats["valid_quotes"],
            "invalid_quotes": stats["invalid_quotes"], "crossed_quotes": stats["crossed_quotes"],
            "invalid_quote_reasons": {k[13:]:v for k,v in stats.items() if k.startswith("invalid_quote:")},
            "timestamp_source_classification": {"event_timestamp_fields": "message.t preferred for trades; message.ts preferred for ob_l1; otherwise alternate field",
              "event_timestamp_units": dict(timestamp_kinds), "receive_timestamp_source": "wrapper.received_at ISO-8601",
              "processing_time_used_as_exchange_time": False},
            "missing_fields": dict(missing), "sample_count": len(samples),
            "periodic_sample_count": stats["periodic_samples"], "event_triggered_sample_count": stats["event_triggered_samples"],
            "periodic_only_sample_count": stats["periodic_only_samples"],
            "event_only_sample_count": stats["event_only_samples"],
            "both_periodic_and_event_sample_count": stats["both_periodic_and_event_samples"],
            "trigger_reason_counts": {k[8:]:v for k,v in stats.items() if k.startswith("trigger:")},
            "trigger_reason_counts_may_overlap": True,
            "inter_sample_receive_gap_seconds": gaps_summary(gaps),
            "data_span_seconds": span, "sample_rows": samples,
            "caveats": ["Finite pass over the recorded file only; no live connection or strategy signals.",
              "The raw source rotates at 10 MB, so results cover only the retained file window and may omit older messages.",
              "Event sampling cooldown uses local receive time; event timestamps are preserved independently.",
              "Trade-triggered samples preserve the trade event and receive timestamps; quote values and quote timestamps are carried separately from the latest valid quote.",
              "Trigger-reason counts may overlap when one sample has multiple trigger reasons."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=str(DEFAULT_SOURCE))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    report = observe(args.source)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("source_path", "source_bytes", "rows_read", "sample_count", "periodic_sample_count", "event_triggered_sample_count", "periodic_only_sample_count", "event_only_sample_count", "both_periodic_and_event_sample_count")}, indent=2))

if __name__ == "__main__": main()
