"""Offline integrity audit for research-only cross-venue gzip JSONL captures.

No network access, no orders, and no production strategy/risk/execution changes.
Delta L2 continuity is checked only with non-decreasing exchange-engine timestamps;
that validates timestamp ordering, not completeness of snapshots.
"""
from __future__ import annotations
import argparse, gzip, json
from pathlib import Path


def audit_delta_continuity(current_record: dict, previous_record: dict) -> bool:
    """Return true when available Delta L2 engine timestamps do not move backwards."""
    curr_ts = current_record.get('timestamp', current_record.get('engine_ts_s'))
    prev_ts = previous_record.get('timestamp', previous_record.get('engine_ts_s'))
    if curr_ts is None or prev_ts is None:
        return False
    try:
        return float(curr_ts) >= float(prev_ts)
    except (TypeError, ValueError):
        return False


def audit_files(paths):
    report = {
        'schema': 'cross_venue_capture_integrity_audit_v1', 'research_only': True,
        'real_orders': False, 'files': [], 'binance_depth': {'rows': 0, 'pu_present': 0,
        'pu_missing': 0, 'continuity_checks': 0, 'continuity_gaps': 0},
        'binance_aggtrade': {'rows': 0, 'backfilled_rows': 0, 'gap_markers': 0,
        'id_gaps': 0, 'duplicates_or_replays': 0, 'first_observed_id': None,
        'last_observed_id': None},
        'delta_l2': {'rows': 0, 'timestamp_missing': 0, 'continuity_checks': 0,
        'timestamp_backwards_or_invalid': 0}, 'malformed_rows': 0,
        'limitations': ['Completeness before the first observed Binance aggregate-trade ID cannot be established.',
        'A successful REST backfill only proves that requested IDs were returned by the public API, not that the websocket session was otherwise uninterrupted.',
        'Non-decreasing Delta L2 timestamps do not prove that no snapshots were lost.']}
    prev_depth_u = None
    expected_trade_id = None
    prev_delta_l2 = None
    for raw_path in paths:
        path = Path(raw_path)
        file_stats = {'path': str(path), 'rows': 0, 'read_error': None}
        report['files'].append(file_stats)
        try:
            stream = gzip.open(path, 'rt', encoding='utf-8', errors='replace')
            with stream:
                for line in stream:
                    file_stats['rows'] += 1
                    try: row = json.loads(line)
                    except (json.JSONDecodeError, TypeError):
                        report['malformed_rows'] += 1; continue
                    if not isinstance(row, dict):
                        report['malformed_rows'] += 1; continue
                    venue, kind = row.get('venue'), row.get('kind')
                    if venue == 'binance' and kind == 'depthUpdate':
                        depth = report['binance_depth']; depth['rows'] += 1
                        pu = row.get('previous_update_id')
                        if pu is None: depth['pu_missing'] += 1
                        else:
                            depth['pu_present'] += 1
                            if prev_depth_u is not None:
                                depth['continuity_checks'] += 1
                                try: ok = int(pu) == int(prev_depth_u)
                                except (TypeError, ValueError): ok = False
                                if not ok: depth['continuity_gaps'] += 1
                        prev_depth_u = row.get('final_update_id')
                    elif venue == 'binance' and kind == 'aggTrade_gap':
                        report['binance_aggtrade']['gap_markers'] += 1
                    elif venue == 'binance' and kind == 'aggTrade':
                        trades = report['binance_aggtrade']; trades['rows'] += 1
                        if row.get('is_backfilled') is True: trades['backfilled_rows'] += 1
                        tid = row.get('trade_id')
                        try: tid = int(tid)
                        except (TypeError, ValueError):
                            trades['id_gaps'] += 1; continue
                        if trades['first_observed_id'] is None:
                            trades['first_observed_id'] = tid
                            expected_trade_id = tid + 1
                        elif expected_trade_id is None:
                            expected_trade_id = tid + 1
                        elif tid == expected_trade_id:
                            expected_trade_id = tid + 1
                        elif tid > expected_trade_id:
                            trades['id_gaps'] += tid - expected_trade_id
                            expected_trade_id = tid + 1
                        else:
                            trades['duplicates_or_replays'] += 1
                        trades['last_observed_id'] = tid
                    elif venue == 'delta' and kind == 'ob_l2_snapshot':
                        delta = report['delta_l2']; delta['rows'] += 1
                        ts = row.get('engine_ts_s', row.get('timestamp'))
                        if ts is None:
                            delta['timestamp_missing'] += 1
                        if prev_delta_l2 is not None:
                            delta['continuity_checks'] += 1
                            if not audit_delta_continuity(row, prev_delta_l2):
                                delta['timestamp_backwards_or_invalid'] += 1
                        prev_delta_l2 = row
        except (OSError, EOFError) as exc:
            file_stats['read_error'] = f'{type(exc).__name__}: {exc}'
    depth = report['binance_depth']; trades = report['binance_aggtrade']; delta = report['delta_l2']
    report['verdict'] = 'PASS' if (report['malformed_rows'] == 0 and depth['rows'] > 0 and
        depth['pu_missing'] == 0 and depth['continuity_gaps'] == 0 and trades['rows'] > 0 and
        trades['gap_markers'] == 0 and trades['id_gaps'] == 0 and trades['duplicates_or_replays'] == 0 and
        delta['rows'] > 0 and delta['timestamp_missing'] == 0 and delta['timestamp_backwards_or_invalid'] == 0 and
        all(f['read_error'] is None for f in report['files'])) else 'FAIL_CLOSED'
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('files', nargs='+', help='one or more finalized .jsonl.gz session partitions')
    parser.add_argument('--output', help='optional JSON report path; existing output is replaced only if explicitly supplied')
    args = parser.parse_args()
    report = audit_files(args.files)
    if args.output:
        Path(args.output).write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(0 if report['verdict'] == 'PASS' else 2)

if __name__ == '__main__': main()
