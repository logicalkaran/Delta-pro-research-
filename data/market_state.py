from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from strategy.fisher import Candle


def _to_float(value: Any, field: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Invalid {field}: {value!r}"
        ) from exc

    if result <= 0:
        raise ValueError(
            f"{field} must be positive: {result}"
        )

    return result


def normalize_candle(raw: Any) -> Candle:

    if isinstance(raw, dict):

        timestamp = (
            raw.get("timestamp")
            or raw.get("time")
            or raw.get("start")
        )

        open_price = raw.get("open")
        high_price = raw.get("high")
        low_price = raw.get("low")
        close_price = raw.get("close")

    elif isinstance(raw, (list, tuple)):

        if len(raw) < 5:
            raise ValueError(
                f"Candle sequence too short: {raw}"
            )

        timestamp = raw[0]
        open_price = raw[1]
        high_price = raw[2]
        low_price = raw[3]
        close_price = raw[4]

    else:
        raise TypeError(
            f"Unsupported candle type: {type(raw).__name__}"
        )

    if timestamp is None:
        raise ValueError(
            f"Candle timestamp missing: {raw}"
        )

    timestamp = int(float(timestamp))

    # Convert microseconds → seconds.
    if timestamp > 10_000_000_000_000:
        timestamp //= 1_000_000

    # Convert milliseconds → seconds.
    elif timestamp > 10_000_000_000:
        timestamp //= 1_000

    candle = Candle(
        timestamp=timestamp,
        open=_to_float(open_price, "open"),
        high=_to_float(high_price, "high"),
        low=_to_float(low_price, "low"),
        close=_to_float(close_price, "close"),
    )

    if candle.high < candle.low:
        raise ValueError(
            f"High below low: {candle}"
        )

    if not (
        candle.low <= candle.open <= candle.high
        and candle.low <= candle.close <= candle.high
    ):
        raise ValueError(
            f"OHLC relationship invalid: {candle}"
        )

    return candle


def aggregate_daily_to_monthly(
    candles: list[Candle],
) -> list[Candle]:
    """
    Aggregate daily candles into calendar-month candles.

    Input:
        Daily Candle objects sorted or unsorted.

    Output:
        One Candle per calendar month.

    The current/incomplete month is NOT removed here.
    The caller decides whether a month is closed.
    """

    if not candles:
        return []

    candles = sorted(
        candles,
        key=lambda c: c.timestamp,
    )

    groups: dict[tuple[int, int], list[Candle]] = {}

    for candle in candles:

        dt = datetime.fromtimestamp(
            candle.timestamp,
            tz=timezone.utc,
        )

        key = (dt.year, dt.month)

        groups.setdefault(key, []).append(candle)

    monthly = []

    for key in sorted(groups):

        rows = groups[key]

        first = rows[0]
        last = rows[-1]

        monthly.append(
            Candle(
                timestamp=first.timestamp,
                open=first.open,
                high=max(c.high for c in rows),
                low=min(c.low for c in rows),
                close=last.close,
            )
        )

    return monthly


def candle_summary(candle: Candle) -> dict[str, Any]:

    return {
        **asdict(candle),
        "utc": datetime.fromtimestamp(
            candle.timestamp,
            tz=timezone.utc,
        ).isoformat(),
    }
