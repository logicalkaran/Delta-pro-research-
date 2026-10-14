import pytest
from research.timestamp_integrity_v1 import normalize_timestamp_ms


def test_explicit_epoch_units_normalize_to_ms():
    assert normalize_timestamp_ms(1_700_000_000, unit='s', now_ms=1_800_000_000_000) == 1_700_000_000_000
    assert normalize_timestamp_ms(1_700_000_000_000, unit='ms', now_ms=1_800_000_000_000) == 1_700_000_000_000
    assert normalize_timestamp_ms(1_700_000_000_000_000, unit='us', now_ms=1_800_000_000_000) == 1_700_000_000_000
    assert normalize_timestamp_ms(1_700_000_000_000_000_000, unit='ns', now_ms=1_800_000_000_000) == 1_700_000_000_000


def test_timezone_aware_iso8601_normalizes():
    assert normalize_timestamp_ms('2023-11-14T22:13:20Z', now_ms=1_800_000_000_000) == 1_700_000_000_000


@pytest.mark.parametrize('value', [None, True, float('nan'), float('inf'), -1, ''])
def test_invalid_values_rejected(value):
    with pytest.raises(ValueError):
        normalize_timestamp_ms(value, unit='ms', now_ms=1_800_000_000_000)


def test_numeric_string_requires_explicit_unit():
    with pytest.raises(ValueError, match='TIMESTAMP_UNIT_REQUIRED'):
        normalize_timestamp_ms('1700000000000', now_ms=1_800_000_000_000)


def test_naive_iso_timestamp_rejected():
    with pytest.raises(ValueError, match='TIMESTAMP_TIMEZONE_REQUIRED'):
        normalize_timestamp_ms('2023-11-14T22:13:20', now_ms=1_800_000_000_000)


def test_future_timestamp_rejected():
    with pytest.raises(ValueError, match='TIMESTAMP_IN_FUTURE'):
        normalize_timestamp_ms(1_900_000_000_000, unit='ms', now_ms=1_800_000_000_000)
