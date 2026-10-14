#!/usr/bin/env python3
"""Strict, offline-only cross-venue integrity + VPIN + derivative + queue batch.

No network access, production imports, credentials, or order execution.
The integrity gate fails closed when timestamps regress, detectable Binance sequence
gaps occur, any non-final gzip partition is damaged, or Delta sequence continuity
cannot be verified from the persisted payload.
"""
from __future__ import annotations
import argparse
import collections
import gzip
import json
import math
import statistics
import sys
import time
import zlib
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIR = ROOT / "data/raw/cross_venue_aligned"
CALIBRATION_S = 900.0
QUEUE_TIMEOUT_S = 0.500
RESPONSE_TARGET_S = 0.200
RESPONSE_MAX_S = 0.500
ROLLING_BUCKETS = 20
NET_MARKOUT_HURDLE_BPS = 4.5
MIN_HOLDOUT_FILLS = 100
DEFAULT_MAKER_FEE_BPS = 2.36
DEFAULT_TAKER_FEE_BPS = 5.90

def finite(value: Any) -> float | None:
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError, OverflowError):
        return None

def write_new_json(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, allow_nan=False)
        fh.write("\n")

def partition_paths(session_id: str, directory: Path) -> list[Path]:
    import re
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", session_id) or ".." in session_id:
        raise ValueError("unsafe session id")
    found = []
    prefix = f"session_{session_id}_part_"
    for p in directory.glob(prefix + "*.jsonl.gz"):
        suffix = p.name[len(prefix):-len(".jsonl.gz")]
        if suffix.isdigit() and p.is_file():
            found.append((int(suffix), p))
    found.sort(key=lambda pair: pair[0])
    if not found:
        raise FileNotFoundError(f"no gzip partitions for session {session_id!r} in {directory}")
    indices = [n for n, _ in found]
    if indices != list(range(1, max(indices) + 1)):
        raise ValueError(f"partition index gap: found {indices}")
    return [p for _, p in found]

def _decode_lines(buffer: bytes, path: Path, line_no: int) -> tuple[list[dict[str, Any]], bytes, int]:
    parts = buffer.split(b"\n")
    tail = parts.pop()
    rows = []
    for raw in parts:
        line_no += 1
        if not raw.strip():
            continue
        try:
            item = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError(f"invalid complete JSONL record {path.name}:{line_no}: {exc}") from exc
        if not isinstance(item, dict):
            raise ValueError(f"expected JSON object {path.name}:{line_no}")
        rows.append(item)
    return rows, tail, line_no

def _gzip_deflate_offset(fh) -> None:
    header = fh.read(10)
    if len(header) != 10 or header[:3] != bytes((0x1f, 0x8b, 0x08)):
        raise ValueError("invalid or truncated gzip header")
    flags = header[3]
    if flags & 0xE0:
        raise ValueError("reserved gzip flags are set")
    if flags & 0x04:
        raw = fh.read(2)
        if len(raw) != 2:
            raise ValueError("truncated gzip extra header")
        extra_len = int.from_bytes(raw, "little")
        if len(fh.read(extra_len)) != extra_len:
            raise ValueError("truncated gzip extra field")
    for bit in (0x08, 0x10):
        if flags & bit:
            while True:
                ch = fh.read(1)
                if not ch:
                    raise ValueError("truncated gzip string header")
                if ch == bytes((0,)):
                    break
    if flags & 0x02 and len(fh.read(2)) != 2:
        raise ValueError("truncated gzip header checksum")

def read_partition(path: Path, is_final: bool, status: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Stream validated JSONL records; recover the complete prefix of a damaged final gzip."""
    pending = b""
    line_no = 0
    damaged = False
    crc = 0
    uncompressed_size = 0
    dec = zlib.decompressobj(-zlib.MAX_WBITS)
    trailer = b""
    with path.open("rb") as fh:
        _gzip_deflate_offset(fh)
        while True:
            chunk = fh.read(4096)
            if not chunk:
                break
            before = dec.copy()
            try:
                out = dec.decompress(chunk)
                crc = zlib.crc32(out, crc)
                uncompressed_size += len(out)
            except (zlib.error, EOFError) as exc:
                if not is_final:
                    raise ValueError(f"damaged non-final partition {path.name}: {exc}") from exc
                damaged = True
                # Retry this final chunk byte-by-byte from the last valid decoder state.
                # Only the corrupt suffix is discarded; prior decoded newline records survive.
                dec = before.copy()
                out = b""
                for byte in chunk:
                    try:
                        piece = dec.decompress(bytes((byte,)))
                    except (zlib.error, EOFError):
                        break
                    out += piece
                    crc = zlib.crc32(piece, crc)
                    uncompressed_size += len(piece)
                rows, pending, line_no = _decode_lines(pending + out, path, line_no)
                for row in rows:
                    yield row
                break
            rows, pending, line_no = _decode_lines(pending + out, path, line_no)
            for row in rows:
                yield row
            if dec.eof:
                trailer = dec.unused_data + fh.read()
                break
    if not damaged and dec.eof:
        if len(trailer) < 8:
            damaged = True
        else:
            expected_crc = int.from_bytes(trailer[:4], "little")
            expected_size = int.from_bytes(trailer[4:8], "little")
            if expected_crc != (crc & 0xFFFFFFFF) or expected_size != (uncompressed_size & 0xFFFFFFFF):
                damaged = True
    elif not dec.eof:
        damaged = True
    if damaged and not is_final:
        raise ValueError(f"damaged non-final gzip partition {path.name}")
    try:
        tail = dec.flush()
    except (zlib.error, EOFError):
        tail = b""
        damaged = True
    if tail:
        crc = zlib.crc32(tail, crc)
        uncompressed_size += len(tail)
    rows, pending, line_no = _decode_lines(pending + tail, path, line_no)
    for row in rows:
        yield row
    if pending:
        if not is_final:
            raise ValueError(f"unterminated JSONL record in non-final partition {path.name}")
        if not damaged:
            raise ValueError(f"valid gzip has unterminated final JSONL record in {path.name}")
        status["dropped_trailing_partial_record_bytes"] = status.get("dropped_trailing_partial_record_bytes", 0) + len(pending)
    status["gzip_integrity"] = "RECOVERED_TRUNCATED_FINAL_PARTITION" if damaged else "VALID"
    status["compressed_bytes"] = path.stat().st_size

def iter_rows(session_id: str, directory: Path, partition_status: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    paths = partition_paths(session_id, directory)
    for i, path in enumerate(paths):
        st: dict[str, Any] = {"partition": path.name, "dropped_trailing_partial_record_bytes": 0}
        partition_status.append(st)
        yield from read_partition(path, i == len(paths) - 1, st)

def imbalance(levels_bid: Any, levels_ask: Any) -> float | None:
    def total(levels):
        if not isinstance(levels, list):
            return None
        vals = []
        for row in levels[:5]:
            if isinstance(row, (list, tuple)) and len(row) >= 2:
                q = finite(row[1])
                if q is None or q < 0:
                    return None
                vals.append(q)
        return sum(vals) if len(vals) == 5 else None
    b, a = total(levels_bid), total(levels_ask)
    if b is None or a is None or b + a <= 0:
        return None
    return (b - a) / (b + a)

def event_time(row: dict[str, Any]) -> float | None:
    for k in ("engine_event_ts_s", "engine_ts_s", "engine_trade_ts_s", "feed_ts_s"):
        v = finite(row.get(k))
        if v is not None and v > 0:
            return v
    return None

def audit_and_calibrate(session_id: str, directory: Path) -> tuple[dict[str, Any], float | None, float | None]:
    statuses: list[dict[str, Any]] = []
    counts = collections.Counter()
    last_ts: dict[tuple[str, str, str], float] = {}
    last_binance_depth_u = None
    binance_depth_previous_id_missing = 0
    binance_depth_previous_id_seen = 0
    last_agg_id = None
    delta_seq_seen = 0
    delta_seq_missing = 0
    last_delta_seq: dict[tuple[str, str], float] = {}
    first_mono = None
    calibration_volume = 0.0
    for row in iter_rows(session_id, directory, statuses):
        counts["records"] += 1
        venue, kind = row.get("venue"), row.get("kind")
        mono = finite(row.get("receive_mono_s"))
        if mono is not None and first_mono is None:
            first_mono = mono
        ts_fields = []
        if venue == "binance":
            for key in ("engine_event_ts_s", "engine_transaction_ts_s"):
                if finite(row.get(key)) is not None:
                    ts_fields.append((key, finite(row.get(key))))
        elif venue == "delta":
            for key in ("engine_ts_s", "engine_trade_ts_s", "feed_ts_s"):
                if finite(row.get(key)) is not None:
                    ts_fields.append((key, finite(row.get(key))))
        for key, ts in ts_fields:
            stream = (str(venue), str(kind), key)
            prior = last_ts.get(stream)
            # Delta trade timestamps can arrive out of order across match events;
            # record this diagnostically but do not treat it as a book-clock regression.
            if key == "engine_trade_ts_s":
                if prior is not None and ts < prior:
                    counts["trade_event_timestamp_out_of_order"] += 1
                last_ts[stream] = ts
                continue
            if prior is not None:
                if ts < prior:
                    counts["timestamp_regressions"] += 1
                elif ts == prior:
                    counts["timestamp_duplicates"] += 1
            last_ts[stream] = ts
        if venue == "binance" and kind == "depthUpdate":
            U, u = finite(row.get("first_update_id")), finite(row.get("final_update_id"))
            pu = finite(row.get("previous_update_id"))
            if U is None or u is None or U > u:
                counts["invalid_depth_sequence_rows"] += 1
            if last_binance_depth_u is not None:
                if pu is None:
                    binance_depth_previous_id_missing += 1
                else:
                    binance_depth_previous_id_seen += 1
                    # USD-M diff-depth continuity is represented by pu == prior u.
                    # U/u ranges may overlap and must not be compared as consecutive IDs.
                    if pu != last_binance_depth_u:
                        counts["binance_depth_sequence_gaps"] += 1
            if u is not None:
                last_binance_depth_u = u
        if venue == "binance" and kind == "aggTrade":
            tid = finite(row.get("trade_id"))
            if tid is not None and last_agg_id is not None and tid > last_agg_id + 1:
                counts["binance_aggtrade_id_gaps"] += 1
            if tid is not None:
                last_agg_id = tid
            qty = finite(row.get("quantity_btc"))
            if mono is not None and first_mono is not None and mono - first_mono < CALIBRATION_S and qty is not None and qty > 0:
                calibration_volume += qty
        if venue == "delta" and kind in ("ob_l1", "ob_l2_snapshot", "trade"):
            seq = next((row.get(k) for k in ("sequence", "seq", "sequence_number", "update_id", "u") if row.get(k) is not None), None)
            # Delta sequence continuity is mandatory for L2 book snapshots. Trade/L1
            # messages may not expose sequence IDs; their engine timestamps are audited separately.
            if seq is None:
                if kind == "ob_l2_snapshot":
                    delta_seq_missing += 1
            else:
                seq_num = finite(seq)
                if seq_num is None:
                    counts["delta_invalid_sequence_values"] += 1
                    if kind == "ob_l2_snapshot": delta_seq_missing += 1
                else:
                    delta_seq_seen += 1
                    skey = (str(kind), "sequence")
                    prior_seq = last_delta_seq.get(skey)
                    if prior_seq is not None:
                        if seq_num < prior_seq:
                            counts["delta_sequence_regressions"] += 1
                        elif seq_num == prior_seq:
                            counts["delta_sequence_duplicates"] += 1
                        elif seq_num > prior_seq + 1:
                            counts["delta_sequence_gaps"] += 1
                    last_delta_seq[skey] = seq_num
    delta_seq_status = "VERIFIABLE" if last_delta_seq.get(("ob_l2_snapshot", "sequence")) is not None and not delta_seq_missing else "UNVERIFIABLE_MISSING_SEQUENCE_FIELDS"
    binance_depth_status = ("VERIFIABLE" if binance_depth_previous_id_seen > 0 and binance_depth_previous_id_missing == 0
                            else "UNVERIFIABLE_MISSING_PREVIOUS_UPDATE_ID")
    detectable_gaps = sum(counts[k] for k in ("binance_depth_sequence_gaps", "binance_aggtrade_id_gaps", "invalid_depth_sequence_rows", "delta_sequence_gaps", "delta_sequence_regressions", "delta_sequence_duplicates", "delta_invalid_sequence_values"))
    audit_pass = (counts["records"] > 0 and counts["timestamp_regressions"] == 0 and detectable_gaps == 0
                  and all(x.get("gzip_integrity") == "VALID" for x in statuses)
                  and delta_seq_status == "VERIFIABLE" and binance_depth_status == "VERIFIABLE")
    bucket_volume = 2.0 * (calibration_volume / 15.0) if calibration_volume > 0 else None
    report = {
        "schema": "offline_cross_venue_integrity_audit_v1", "session_id": session_id,
        "status": "PASS" if audit_pass else "FAIL_CLOSED",
        "strict_sequence_continuity_verified": delta_seq_status == "VERIFIABLE" and binance_depth_status == "VERIFIABLE" and detectable_gaps == 0,
        "delta_sequence_status": delta_seq_status, "delta_sequence_fields_seen": delta_seq_seen,
        "delta_sequence_fields_missing": delta_seq_missing, "binance_depth_sequence_status": binance_depth_status,
        "binance_depth_previous_id_seen": binance_depth_previous_id_seen,
        "binance_depth_previous_id_missing": binance_depth_previous_id_missing, "counts": dict(counts),
        "partition_status": statuses, "first_receive_mono_s": first_mono,
        "calibration_seconds": CALIBRATION_S, "binance_aggressive_volume_first_15m_btc": calibration_volume,
        "mean_aggressive_volume_per_minute_btc": calibration_volume / 15.0,
        "dynamic_vpin_bucket_volume_btc": bucket_volume,
        "gate_reasons": ([ "no_records" ] if counts["records"] == 0 else [])
            + ([ "matching_engine_timestamp_regression" ] if counts["timestamp_regressions"] else [])
            + ([ "sequence_gap_or_invalid_sequence" ] if detectable_gaps else [])
            + ([ "gzip_integrity_not_valid" ] if any(x.get("gzip_integrity") != "VALID" for x in statuses) else [])
            + ([ "binance_depth_continuity_unverifiable" ] if binance_depth_status != "VERIFIABLE" else [])
            + ([ "delta_sequence_continuity_unverifiable" ] if delta_seq_status != "VERIFIABLE" else [])
            + ([ "no_calibration_volume" ] if bucket_volume is None else []),
        "research_only": True, "real_orders": False
    }
    if bucket_volume is None:
        report["status"] = "FAIL_CLOSED"
        report["gate_reasons"].append("no_calibration_volume")
    return report, bucket_volume, first_mono

def run_offline(session_id: str, directory: Path, output_dir: Path, bucket_volume: float,
                first_mono: float, order_size: float, maker_fee: float, taker_fee: float) -> dict[str, Any]:
    paths = partition_paths(session_id, directory)
    prefix = output_dir / f"cross_venue_{session_id}"
    vpin_path = prefix.with_name(prefix.name + "_vpin_buckets.jsonl")
    derivative_path = prefix.with_name(prefix.name + "_derivative.jsonl")
    queue_path = prefix.with_name(prefix.name + "_queue_replay.jsonl")
    econ_path = prefix.with_name(prefix.name + "_economic_fills.jsonl")
    for p in (vpin_path, derivative_path, queue_path, econ_path):
        if p.exists():
            raise FileExistsError(f"refusing to overwrite existing research output: {p}")
    output_dir.mkdir(parents=True, exist_ok=True)
    recent_vpin = collections.deque(maxlen=ROLLING_BUCKETS)
    bucket_id = 0
    buy = sell = in_bucket = 0.0
    total_bucket_trade_volume = 0.0
    latest_vpin_allowed: bool | None = None
    latest_vpin_status = "UNKNOWN"
    current_binance_book = None
    delta_books = collections.deque(maxlen=3000)
    pending_responses: list[dict[str, Any]] = []
    active_quote = None
    pending_marks: list[dict[str, Any]] = []
    fill_rows: list[dict[str, Any]] = []
    counters = collections.Counter()
    last_record_mono = first_mono
    eligible_after = first_mono + CALIBRATION_S
    fees_bps = maker_fee + taker_fee

    def write_jsonl(fh, obj):
        fh.write(json.dumps(obj, separators=(",", ":"), allow_nan=False) + "\n")

    with vpin_path.open("x", encoding="utf-8") as vf, derivative_path.open("x", encoding="utf-8") as df, queue_path.open("x", encoding="utf-8") as qf, econ_path.open("x", encoding="utf-8") as ef:
        def complete_bucket():
            nonlocal bucket_id, buy, sell, in_bucket, latest_vpin_allowed, latest_vpin_status
            if in_bucket < bucket_volume - 1e-9:
                return
            bucket_id += 1
            value = abs(buy - sell) / bucket_volume
            threshold = statistics.quantiles(list(recent_vpin), n=10, method="inclusive")[8] if len(recent_vpin) == ROLLING_BUCKETS else None
            status = "READY" if threshold is not None else "UNKNOWN"
            critical = (value > threshold) if threshold is not None else None
            latest_vpin_allowed = (not critical) if critical is not None else None
            latest_vpin_status = "CRITICAL_TOXICITY" if critical else "NORMAL" if critical is not None else "UNKNOWN"
            write_jsonl(vf, {"schema":"dynamic_vpin_bucket_v1","session_id":session_id,"bucket_id":bucket_id,
                "bucket_volume_btc":bucket_volume,"buy_volume_btc":buy,"sell_volume_btc":sell,
                "vpin":value,"threshold_p90_preceding_20":threshold,"status":status,
                "passive_making_allowed": (not critical) if critical is not None else None,
                "decision":"CRITICAL_TOXICITY" if critical else "NORMAL" if critical is not None else "UNKNOWN",
                "calibration_seconds":CALIBRATION_S,"real_orders":False})
            recent_vpin.append(value)
            buy = sell = in_bucket = 0.0

        def expire_quote(at, reason):
            nonlocal active_quote
            if active_quote is not None:
                write_jsonl(qf, {"schema":"pessimistic_queue_replay_v1","session_id":session_id,
                    "trigger_receive_mono_s":active_quote["trigger_mono"],"status":"EXPIRED_UNFILLED",
                    "reason":reason,"limit_price":active_quote["limit_price"],
                    "queue_ahead_initial":active_quote["queue_ahead"],"aggressive_sell_volume":active_quote["sell_volume"],
                    "order_size_contract_units":order_size,"elapsed_ms":max(0.0,(at-active_quote["trigger_mono"])*1000),
                    "real_orders":False})
                counters["expired_unfilled"] += 1
                active_quote = None

        def finish_fill(at, book):
            nonlocal active_quote
            quote = active_quote
            if quote is None:
                return
            mid = book.get("mid")
            if mid is None or mid <= 0:
                expire_quote(at, "FILL_WITHOUT_VALID_MID")
                return
            capture = (mid - quote["limit_price"]) / mid * 10000.0
            fill = {"schema":"simulated_holdout_fill_v1","session_id":session_id,
                "trigger_receive_mono_s":quote["trigger_mono"],"fill_receive_mono_s":at,
                "fill_price":quote["limit_price"],"mid_at_fill":mid,"spread_capture_bps":capture,
                "directional_markout_15s_bps":None,"fees_bps":fees_bps,"net_markout_15s_bps":None,
                "markout_due_mono_s":at+15.0,"queue_ahead_initial":quote["queue_ahead"],
                "order_size_contract_units":order_size,"queue_sell_volume":quote["sell_volume"],
                "fill_reason":"EXACT_TIER_AGGRESSIVE_SELL_DEPLETION","real_orders":False}
            pending_marks.append(fill)
            fill_rows.append(fill)
            counters["next_independent_trigger_mono"] = at + 15.0
            write_jsonl(qf, {"schema":"pessimistic_queue_replay_v1","session_id":session_id,
                "trigger_receive_mono_s":quote["trigger_mono"],"status":"SIMULATED_FILL",
                "fill_receive_mono_s":at,"limit_price":quote["limit_price"],
                "queue_ahead_initial":quote["queue_ahead"],"aggressive_sell_volume":quote["sell_volume"],
                "order_size_contract_units":order_size,"spread_capture_bps":capture,"real_orders":False})
            counters["simulated_fills"] += 1
            active_quote = None

        for row in iter_rows(session_id, directory, []):
            counters["input_rows"] += 1
            venue, kind = row.get("venue"), row.get("kind")
            mono = finite(row.get("receive_mono_s"))
            ets = event_time(row)
            if mono is not None:
                last_record_mono = max(last_record_mono, mono)
            if venue == "binance" and kind == "aggTrade":
                qty, side = finite(row.get("quantity_btc")), row.get("aggressor_side")
                if qty is not None and qty > 0 and side in ("BUY", "SELL"):
                    remain = qty
                    while remain > 1e-12:
                        take = min(remain, bucket_volume - in_bucket)
                        if side == "BUY": buy += take
                        else: sell += take
                        in_bucket += take
                        remain -= take
                        total_bucket_trade_volume += take
                        if in_bucket >= bucket_volume - 1e-9:
                            complete_bucket()
                # Candidate event is only evaluated in holdout after calibration.
                if side == "SELL" and mono is not None and mono >= eligible_after:
                    b = current_binance_book
                    pre = next((x for x in reversed(delta_books) if x["mono"] <= mono), None)
                    reason = None
                    if not row.get("book_synced") or b is None or b.get("mono", mono) > mono or mono - b["mono"] > RESPONSE_TARGET_S:
                        reason = "BINANCE_BOOK_MISSING_OR_STALE"
                    elif pre is None or mono - pre["mono"] > RESPONSE_TARGET_S:
                        reason = "NO_FRESH_PRE_DELTA_BOOK"
                    elif ets is None or pre.get("engine_ts") is None or pre["engine_ts"] > ets:
                        reason = "SKIP_DELTA_ALREADY_MOVED_OR_CLOCK_ORDER_INVALID"
                    elif b.get("i5") is None or pre.get("i5") is None:
                        reason = "FIVE_LEVEL_IMBALANCE_UNAVAILABLE"
                    i_b = b.get("i5") if reason is None else None
                    i_d = pre.get("i5") if reason is None else None
                    diff = i_b - i_d if i_b is not None and i_d is not None else None
                    candidate = bool(reason is None and i_b > 0.6 and i_d <= 0.2 and diff > 0.4)
                    if reason is None and not candidate: reason = "IMBALANCE_THRESHOLDS_NOT_MET"
                    event = {"schema":"cross_venue_derivative_v1","session_id":session_id,
                        "trigger_receive_mono_s":mono,"binance_engine_ts_s":ets,"trade_id":row.get("trade_id"),
                        "binance_sell_quantity_btc":qty,"binance_imbalance_5":i_b,"delta_pre_imbalance_5":i_d,
                        "imbalance_difference":diff,"delta_pre_receive_mono_s":pre.get("mono") if pre else None,
                        "delta_pre_engine_ts_s":pre.get("engine_ts") if pre else None,
                        "vpin_status":latest_vpin_status,"vpin_passive_making_allowed":latest_vpin_allowed,
                        "candidate":candidate,"decision":"CANDIDATE" if candidate else "SKIP",
                        "reason":None if candidate else reason,"response_200ms":None,"real_orders":False}
                    if candidate:
                        pending_responses.append(event)
                        counters["derivative_candidates"] += 1
                        if latest_vpin_allowed is not True:
                            counters["queue_vpin_unknown_abstain" if latest_vpin_allowed is None else "queue_vpin_toxicity_veto"] += 1
                        elif active_quote is None and mono >= eligible_after and mono >= counters.get("next_independent_trigger_mono", eligible_after):
                            bids = pre.get("bids", [])
                            limit_price = finite(bids[0][0]) if bids and len(bids[0]) > 1 else None
                            q_ahead = finite(bids[0][1]) if bids and len(bids[0]) > 1 else None
                            if limit_price and q_ahead is not None and q_ahead >= 0:
                                active_quote = {"trigger_mono":mono,"limit_price":limit_price,"queue_ahead":q_ahead,
                                    "sell_volume":0.0,"initial_bid":pre.get("bid"),"initial_ask":pre.get("ask"),
                                    "initial_mid":pre.get("mid"),"deadline":mono+QUEUE_TIMEOUT_S}
                                counters["orders_armed"] += 1
                    if not candidate:
                        write_jsonl(df, event)
            elif venue == "binance" and kind == "depthUpdate":
                if row.get("book_synced") is True:
                    current_binance_book = {"mono":mono,"engine_ts":ets,"i5":imbalance(row.get("bid_levels_top5_btc"),row.get("ask_levels_top5_btc"))}
            elif venue == "delta" and kind == "ob_l2_snapshot":
                bids, asks = row.get("bid_levels"), row.get("ask_levels")
                bid = finite(row.get("best_bid")); ask = finite(row.get("best_ask"))
                mid = (bid + ask) / 2 if bid and ask and ask >= bid else None
                book = {"mono":mono,"engine_ts":ets,"bids":bids if isinstance(bids,list) else [],
                    "asks":asks if isinstance(asks,list) else [],"bid":bid,"ask":ask,"mid":mid,
                    "i5":imbalance(bids, asks)}
                if mono is not None:
                    delta_books.append(book)
                    for event in list(pending_responses):
                        age = mono - event["trigger_receive_mono_s"]
                        if age >= RESPONSE_TARGET_S:
                            if age <= RESPONSE_MAX_S:
                                event["response_200ms"] = {"observed_delay_ms":age*1000,
                                    "delta_post_imbalance_5":book["i5"],
                                    "delta_imbalance_change_200ms":(book["i5"]-event["delta_pre_imbalance_5"] if book["i5"] is not None and event["delta_pre_imbalance_5"] is not None else None)}
                                event["decision"] = "CANDIDATE_WITH_200MS_RESPONSE"
                            else:
                                event["decision"] = "CANDIDATE_NO_RESPONSE_SNAPSHOT"
                            write_jsonl(df, event)
                            pending_responses.remove(event)
                    # Existing fill markouts use the first Delta L2 snapshot at/after 15 seconds.
                    for fill in list(pending_marks):
                        if mono >= fill["markout_due_mono_s"]:
                            if mid is not None and fill["mid_at_fill"] > 0:
                                direction = (mid - fill["mid_at_fill"]) / fill["mid_at_fill"] * 10000.0
                                fill["directional_markout_15s_bps"] = direction
                                fill["net_markout_15s_bps"] = fill["spread_capture_bps"] + direction - fees_bps
                                write_jsonl(ef, fill)
                                counters["completed_15s_markouts"] += 1
                            pending_marks.remove(fill)
                    # Pessimistic queue: any downward best-quote shift cancels; deadline is 500 ms.
                    if active_quote is not None:
                        age = mono - active_quote["trigger_mono"]
                        adverse = ((bid is not None and active_quote["initial_bid"] is not None and bid < active_quote["initial_bid"])
                                   or (ask is not None and active_quote["initial_ask"] is not None and ask < active_quote["initial_ask"]))
                        if adverse:
                            expire_quote(mono, "ADVERSE_BEST_QUOTE_SHIFT")
                        elif age >= QUEUE_TIMEOUT_S:
                            expire_quote(mono, "500MS_TIMEOUT")
                    if active_quote is None and pending_marks:
                        counters["next_independent_trigger_mono"] = max(x["markout_due_mono_s"] for x in pending_marks)
            elif venue == "delta" and kind == "trade":
                if active_quote is not None and mono is not None:
                    age = mono - active_quote["trigger_mono"]
                    if age >= QUEUE_TIMEOUT_S:
                        expire_quote(mono, "500MS_TIMEOUT")
                    elif age >= 0 and row.get("role") == "m" and finite(row.get("price")) == active_quote["limit_price"]:
                        q = finite(row.get("quantity_contract_units"))
                        if q is not None and q > 0:
                            active_quote["sell_volume"] += q
                            if active_quote["sell_volume"] >= active_quote["queue_ahead"] + order_size:
                                # Use most recent pre-fill book; no interpolation.
                                book = delta_books[-1] if delta_books else None
                                if book:
                                    finish_fill(mono, book)
                                else:
                                    expire_quote(mono, "FILL_WITHOUT_VALID_BOOK")
        if active_quote is not None:
            expire_quote(last_record_mono, "END_OF_ARCHIVE")
        for event in pending_responses:
            event["decision"] = "CANDIDATE_NO_RESPONSE_SNAPSHOT"
            write_jsonl(df, event)
        for fill in pending_marks:
            # Incomplete markouts are deliberately excluded from the hurdle statistic.
            fill["net_markout_15s_bps"] = None
            write_jsonl(ef, fill)
        if in_bucket > 0:
            counters["incomplete_final_vpin_bucket_volume_btc"] = in_bucket
    values = [x["net_markout_15s_bps"] for x in fill_rows if x["net_markout_15s_bps"] is not None]
    median_net = statistics.median(values) if values else None
    summary = {
        "schema":"offline_cross_venue_batch_v1","session_id":session_id,"status":"COMPLETE_RESEARCH_ONLY",
        "calibration":{"duration_seconds":CALIBRATION_S,"aggressive_volume_btc":bucket_volume * 15.0 / 2.0,
            "bucket_volume_btc":bucket_volume,"vpin_rolling_baseline_buckets":ROLLING_BUCKETS,
            "threshold":"90th percentile of strictly preceding 20 completed VPIN buckets; UNKNOWN until bucket 21"},
        "derivative":{"response_target_ms":RESPONSE_TARGET_S*1000,"response_max_ms":RESPONSE_MAX_S*1000,
            "binance_i5_gt":0.6,"delta_i5_lte":0.2,"difference_gt":0.4,"candidate_count":counters["derivative_candidates"]},
        "queue_replay":{"timeout_ms":QUEUE_TIMEOUT_S*1000,"order_size_contract_units":order_size,
            "orders_armed":counters["orders_armed"],"simulated_fills":counters["simulated_fills"],
            "expired_unfilled":counters["expired_unfilled"]},
        "economics":{"sample_count":len(values),"median_15s_net_markout_bps":median_net,
            "hurdle_bps":NET_MARKOUT_HURDLE_BPS,"minimum_independent_holdout_fills":MIN_HOLDOUT_FILLS,
            "pass":bool(len(values)>=MIN_HOLDOUT_FILLS and median_net is not None and median_net>=NET_MARKOUT_HURDLE_BPS),
            "fees_bps":fees_bps,"formula":"spread_capture_bps + directional_mid_markout_15s_bps - maker_fee_bps - taker_fee_bps",
            "independence_note":"one hypothetical quote at a time; 15-second markout windows are used as the minimum separation proxy"},
        "counts":dict(counters),"outputs":{"vpin":str(vpin_path),"derivative":str(derivative_path),"queue":str(queue_path),"economic_fills":str(econ_path)},
        "limitations":["Delta trade role 'm' is treated as aggressive sell only as a provisional feed convention.",
            "Cross-venue engine timestamps may have clock offsets; candidates with Delta engine time after the Binance trigger are skipped.",
            "Simulated fills are not exchange-confirmed fills. Delta depth units are contract units.",
            "A recovered truncated final gzip partition is not eligible for strict audit PASS.",
            "This report is research only; no production code or execution authority is imported."]
    }
    return summary

def pre_depth_size(books, event):
    pre_mono = event.get("delta_pre_receive_mono_s")
    for b in reversed(books):
        if b["mono"] == pre_mono and b.get("bids"):
            return finite(b["bids"][0][1])
    return None

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--session-id", default="cross_venue_20261009T200244Z")
    ap.add_argument("--archive-dir", type=Path, default=DEFAULT_DIR)
    ap.add_argument("--output-dir", type=Path, default=ROOT / "data/processed")
    ap.add_argument("--capture-pid", type=int, default=None, help="wait for this exact capture PID to exit before audit")
    ap.add_argument("--order-size-contracts", type=float, default=1.0)
    ap.add_argument("--maker-fee-bps", type=float, default=DEFAULT_MAKER_FEE_BPS)
    ap.add_argument("--taker-fee-bps", type=float, default=DEFAULT_TAKER_FEE_BPS)
    args = ap.parse_args()
    if args.order_size_contracts <= 0 or args.maker_fee_bps < 0 or args.taker_fee_bps < 0:
        ap.error("order size must be positive and fees non-negative")
    if args.capture_pid:
        pidfile = Path(f"/proc/{args.capture_pid}/cmdline")
        while pidfile.exists():
            try:
                cmd = pidfile.read_bytes().replace(b"\0", b" ").decode(errors="replace")
            except OSError:
                break
            if "cross_venue_aligned_capture_v1.py" not in cmd:
                break
            print(f"Waiting for research capture PID {args.capture_pid} to exit...", flush=True)
            time.sleep(30)
    audit, bucket_volume, first_mono = audit_and_calibrate(args.session_id, args.archive_dir)
    audit_path = args.output_dir / f"cross_venue_{args.session_id}_integrity_audit.json"
    try:
        write_new_json(audit_path, audit)
    except FileExistsError:
        print(f"Refusing to overwrite audit report: {audit_path}", file=sys.stderr)
        return 2
    print(json.dumps({"integrity_audit":str(audit_path),"status":audit["status"],"gate_reasons":audit["gate_reasons"]},indent=2))
    if audit["status"] != "PASS":
        print("FAILED_CLOSED: no VPIN, derivative, queue, or economic batch was run.", file=sys.stderr)
        return 3
    summary = run_offline(args.session_id, args.archive_dir, args.output_dir, bucket_volume, first_mono,
                          args.order_size_contracts, args.maker_fee_bps, args.taker_fee_bps)
    summary["integrity_audit"] = str(audit_path)
    summary_path = args.output_dir / f"cross_venue_{args.session_id}_offline_batch_summary.json"
    try:
        write_new_json(summary_path, summary)
    except FileExistsError:
        print(f"Refusing to overwrite summary: {summary_path}", file=sys.stderr)
        return 2
    print(json.dumps(summary, indent=2, allow_nan=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
