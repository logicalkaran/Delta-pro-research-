"""Strict timestamp normalization for research ingestion; no production wiring."""
from datetime import datetime, timezone
import math

MAX_EPOCH_MS = 253402300799999


def normalize_timestamp_ms(value, *, unit=None, now_ms=None, future_tolerance_ms=1000):
    if value is None or isinstance(value, bool):
        raise ValueError('TIMESTAMP_MISSING_OR_INVALID')
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            raise ValueError('TIMESTAMP_MISSING_OR_INVALID')
        try:
            numeric = float(raw)
        except ValueError:
            try:
                parsed = datetime.fromisoformat(raw.replace('Z', '+00:00'))
            except ValueError:
                raise ValueError('TIMESTAMP_ISO8601_INVALID') from None
            if parsed.tzinfo is None:
                raise ValueError('TIMESTAMP_TIMEZONE_REQUIRED')
            result = int(parsed.astimezone(timezone.utc).timestamp() * 1000)
            return _validate(result, now_ms, future_tolerance_ms)
        value = numeric
    if not isinstance(value, (int, float)):
        raise ValueError('TIMESTAMP_TYPE_INVALID')
    numeric = float(value)
    if not math.isfinite(numeric) or numeric < 0:
        raise ValueError('TIMESTAMP_NUMERIC_INVALID')
    if unit not in {'s', 'ms', 'us', 'ns'}:
        raise ValueError('TIMESTAMP_UNIT_REQUIRED')
    result = numeric * {'s': 1000, 'ms': 1, 'us': 0.001, 'ns': 0.000001}[unit]
    if not math.isfinite(result) or result > MAX_EPOCH_MS:
        raise ValueError('TIMESTAMP_OUT_OF_RANGE')
    return _validate(int(result), now_ms, future_tolerance_ms)


def _validate(result, now_ms, tolerance):
    if result < 0 or result > MAX_EPOCH_MS:
        raise ValueError('TIMESTAMP_OUT_OF_RANGE')
    if isinstance(tolerance, bool) or not isinstance(tolerance, int) or tolerance < 0:
        raise ValueError('TIMESTAMP_TOLERANCE_INVALID')
    reference = int(datetime.now(timezone.utc).timestamp() * 1000) if now_ms is None else now_ms
    if isinstance(reference, bool) or not isinstance(reference, int) or reference < 0:
        raise ValueError('REFERENCE_TIME_INVALID')
    if result > reference + tolerance:
        raise ValueError('TIMESTAMP_IN_FUTURE')
    return result
