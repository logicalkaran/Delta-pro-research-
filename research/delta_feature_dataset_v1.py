#!/usr/bin/env python3
"""Build timestamp-aligned, no-lookahead feature rows from a saved Delta public snapshot.

Research-only offline transform. Candle timestamps are treated as bar OPEN times;
features become available at bar close, and the target is the NEXT bar close return.
Current ticker/order-book values are intentionally excluded from historical rows.
"""
from __future__ import annotations
import argparse, hashlib, json, math, os, tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

INTERVALS = {"1m": 60, "5m": 300, "1h": 3600}
WINDOWS = (10, 20, 60)


def finite(x: Any) -> float | None:
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def _series(snapshot: dict[str, Any], symbol: str, kind: str, resolution: str) -> list[dict[str, Any]]:
    key = f"{symbol.upper()}|{kind}|{resolution}"
    obj = snapshot.get("candle_sets", {}).get(key, {})
    rows = obj.get("candles", []) if isinstance(obj, dict) else []
    clean = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        ts = finite(r.get("time", r.get("timestamp")))
        o, h, l, c = (finite(r.get(k)) for k in ("open", "high", "low", "close"))
        vol = finite(r.get("volume"))
        if ts is None or any(v is None for v in (o, h, l, c)):
            continue
        if kind != "funding" and min(o, h, l, c) <= 0:
            continue
        if h < max(o, l, c) or l > min(o, h, c):
            continue
        clean.append({"time": int(ts), "open": o, "high": h, "low": l, "close": c, "volume": vol})
    # Deduplicate deterministically; last row wins for a duplicate timestamp.
    by_ts = {r["time"]: r for r in clean}
    return [by_ts[t] for t in sorted(by_ts)]


def _latest_asof(rows: list[dict[str, Any]], times: list[int], ts: int) -> dict[str, Any] | None:
    """Return latest row whose CLOSE timestamp is <= ts (no lookahead)."""
    lo, hi = 0, len(times)
    while lo < hi:
        mid = (lo + hi) // 2
        if times[mid] <= ts: lo = mid + 1
        else: hi = mid
    return rows[lo - 1] if lo else None


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _std(values: list[float]) -> float | None:
    if len(values) < 2: return None
    m = sum(values) / len(values)
    return math.sqrt(sum((x-m)**2 for x in values)/(len(values)-1))


def _safe_bps(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or a <= 0 or b <= 0: return None
    return (a / b - 1.0) * 10000.0


def build(snapshot: dict[str, Any], symbol: str = "BTCUSD") -> dict[str, Any]:
    symbol = symbol.upper()
    all_rows: list[dict[str, Any]] = []
    diagnostics: dict[str, Any] = {}
    cutoff_ts = None
    collected_at = snapshot.get("collected_at")
    if isinstance(collected_at, str):
        try:
            cutoff_ts = int(datetime.fromisoformat(collected_at.replace("Z", "+00:00")).timestamp())
        except ValueError:
            cutoff_ts = None
    for resolution, seconds in INTERVALS.items():
        prices = _series(snapshot, symbol, "price", resolution)
        marks = _series(snapshot, symbol, "mark", "1m")
        funding = _series(snapshot, symbol, "funding", "1h")
        oi = _series(snapshot, symbol, "open_interest", "1h")
        # Drop in-progress bars. The last candle returned by an exchange can
        # be the currently forming bar, whose final close/volume is unknowable.
        if cutoff_ts is not None:
            prices = [r for r in prices if r["time"] + seconds <= cutoff_ts]
            marks = [r for r in marks if r["time"] + 60 <= cutoff_ts]
            funding = [r for r in funding if r["time"] + 3600 <= cutoff_ts]
            oi = [r for r in oi if r["time"] + 3600 <= cutoff_ts]
        mark_times = [r["time"] + 60 for r in marks]
        funding_times = [r["time"] + 3600 for r in funding]
        oi_times = [r["time"] + 3600 for r in oi]
        closes = [r["close"] for r in prices]
        returns = [None] + [math.log(closes[i]/closes[i-1]) if closes[i] > 0 and closes[i-1] > 0 else None for i in range(1, len(closes))]
        volumes = [r["volume"] for r in prices]
        for i, bar in enumerate(prices):
            # Candle time is the bar OPEN. Its close/volume are only usable at close_ts.
            close_ts = bar["time"] + seconds
            feat: dict[str, Any] = {
                "schema_version": 1, "symbol": symbol, "timeframe": resolution,
                "bar_open_ts": bar["time"], "feature_available_ts": close_ts,
                "open": bar["open"], "high": bar["high"], "low": bar["low"], "close": bar["close"],
                "volume": bar["volume"], "return_1_bps": _safe_bps(bar["close"], prices[i-1]["close"]) if i else None,
                "candle_range_bps": ((bar["high"]-bar["low"])/bar["close"]*10000) if bar["close"] > 0 else None,
                "body_bps": ((bar["close"]-bar["open"])/bar["open"]*10000) if bar["open"] > 0 else None,
                "close_location": ((bar["close"]-bar["low"])/(bar["high"]-bar["low"])) if bar["high"] > bar["low"] else 0.5,
            }
            for lag in (3, 5, 10):
                feat[f"return_{lag}_bps"] = _safe_bps(bar["close"], prices[i-lag]["close"]) if i >= lag else None
            for window in WINDOWS:
                hist = [x for x in returns[max(1, i-window+1):i+1] if x is not None]
                feat[f"realized_vol_{window}_bars_bps"] = (_std(hist) * 10000 * math.sqrt(window)) if len(hist) >= max(3, window//2) else None
                vh = [v for v in volumes[max(0, i-window+1):i+1] if v is not None and v >= 0]
                vm, vs = _mean(vh), _std(vh)
                feat[f"volume_zscore_{window}"] = ((bar["volume"]-vm)/vs) if bar["volume"] is not None and vs and vs > 0 and len(vh) >= max(3, window//2) else None
            mark = _latest_asof(marks, mark_times, close_ts)
            frow = _latest_asof(funding, funding_times, close_ts)
            orow = _latest_asof(oi, oi_times, close_ts)
            feat["mark_close_asof"] = mark["close"] if mark else None
            feat["mark_basis_bps_asof"] = _safe_bps(mark["close"], bar["close"]) if mark else None
            feat["funding_rate_asof"] = frow["close"] if frow else None
            feat["open_interest_asof"] = orow["close"] if orow else None
            # Compare with the latest prior hourly observation, not a future candle.
            prev_oi = _latest_asof(oi, oi_times, close_ts - 3600) if orow else None
            feat["open_interest_change_pct_1h_asof"] = ((orow["close"]/prev_oi["close"]-1)*100) if orow and prev_oi and prev_oi["close"] > 0 else None
            # Target starts only after all features are available: next bar close vs current close.
            nxt = prices[i+1] if i+1 < len(prices) else None
            feat["target_next_bar_return_bps"] = _safe_bps(nxt["close"], bar["close"]) if nxt else None
            feat["target_next_bar_direction"] = (1 if nxt["close"] > bar["close"] else (-1 if nxt["close"] < bar["close"] else 0)) if nxt else None
            feat["target_available_ts"] = nxt["time"] + seconds if nxt else None
            all_rows.append(feat)
        diagnostics[resolution] = {"input_bars": len(prices), "rows_with_next_target": max(0, len(prices)-1), "rows_without_target": 1 if prices else 0}
    all_rows.sort(key=lambda r: (r["feature_available_ts"], r["timeframe"]))
    return {
        "schema_version": 1, "dataset": "delta_public_features_v1", "symbol": symbol,
        "source_snapshot_collected_at": snapshot.get("collected_at"),
        "built_at": datetime.now(timezone.utc).isoformat(),
        "row_count": len(all_rows), "timeframe_diagnostics": diagnostics, "rows": all_rows,
        "methodology": {
            "candle_timestamp_interpretation": "bar_open_time",
            "incomplete_bars": "excluded when bar close time is later than snapshot collected_at",
            "feature_availability": "bar_close_time; auxiliary series joined only when their bar close is <= feature_available_ts",
            "target": "next price candle close return in bps; target is not a feature",
            "lookahead_controls": ["current ticker excluded", "current order book excluded", "auxiliary candles use close-time as-of join", "target begins after feature availability"],
            "limitations": ["snapshot only; not independent out-of-sample validation", "no historical order-book tape", "funding units and OI contract semantics require exchange-spec verification", "price candle volume units require contract-spec verification"],
        },
        "authority": {"research_only": True, "paper_only": True, "real_orders": False, "production_strategy_changed": False},
    }


def write_dataset(dataset: dict[str, Any], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(dataset, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    digest = hashlib.sha256(raw).hexdigest()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = output_dir / f"delta_feature_dataset_{dataset['symbol']}_{stamp}.jsonl"
    fd, tmp = tempfile.mkstemp(prefix=out.name+".", suffix=".tmp", dir=str(output_dir))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps({"_metadata": {k:v for k,v in dataset.items() if k != "rows"}, "sha256_dataset_before_hash_field": digest}, separators=(",", ":")) + "\n")
            for row in dataset["rows"]:
                f.write(json.dumps(row, separators=(",", ":"), allow_nan=False) + "\n")
            f.flush(); os.fsync(f.fileno())
        os.replace(tmp, out)
    except BaseException:
        try: os.unlink(tmp)
        except OSError: pass
        raise
    return out


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("snapshot",type=Path); p.add_argument("--symbol",default="BTCUSD"); p.add_argument("--output-dir",default="data/processed")
    a=p.parse_args()
    try:
        snap=json.loads(a.snapshot.read_text(encoding="utf-8")); ds=build(snap,a.symbol); out=write_dataset(ds,Path(a.output_dir))
        print(json.dumps({"output":str(out),"symbol":ds["symbol"],"row_count":ds["row_count"],"timeframes":ds["timeframe_diagnostics"],"source_snapshot_collected_at":ds["source_snapshot_collected_at"],"research_only":True,"real_orders":False},indent=2)); return 0
    except Exception as e:
        print(json.dumps({"status":"FAILED_CLOSED","error_type":type(e).__name__,"message":str(e)[:180],"real_orders":False},indent=2)); return 2

if __name__ == "__main__": raise SystemExit(main())
