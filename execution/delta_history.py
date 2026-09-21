import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from execution.delta_client import DeltaPublicClient
from data.market_state import normalize_candle


class DeltaDailyHistory:

    def __init__(self, client=None, symbol="BTCUSD"):
        self.client = client or DeltaPublicClient()
        self.symbol = symbol

    def fetch(self, start: int, end: int):

        if start >= end:
            raise ValueError("start must be before end")

        DAY = 24 * 60 * 60
        CHUNK_DAYS = 900

        candles_by_timestamp = {}

        cursor_end = end
        page = 0

        while cursor_end > start:

            page += 1

            cursor_start = max(
                start,
                cursor_end - CHUNK_DAYS * DAY,
            )

            response = self.client.get_candles(
                symbol=self.symbol,
                resolution="1d",
                start=cursor_start,
                end=cursor_end,
            )

            raw = response.get("result", [])

            if not raw:
                print(
                    f"page={page:02d} rows=0 "
                    f"range={cursor_start}->{cursor_end}"
                )
                break

            candles = sorted(
                (
                    normalize_candle(row)
                    for row in raw
                ),
                key=lambda c: c.timestamp,
            )

            before = len(candles_by_timestamp)

            for candle in candles:
                if start <= candle.timestamp <= end:
                    candles_by_timestamp[candle.timestamp] = candle

            after = len(candles_by_timestamp)
            new_rows = after - before

            first_ts = candles[0].timestamp
            last_ts = candles[-1].timestamp

            print(
                f"page={page:02d} "
                f"rows={len(candles):4d} "
                f"new={new_rows:4d} "
                f"first={first_ts} "
                f"last={last_ts}"
            )

            # We have reached the requested beginning.
            if first_ts <= start:
                break

            # If this page contributes no new candles, the API has
            # reached its historical boundary for this request.
            if new_rows == 0:
                print(
                    "No new historical candles returned; "
                    "stopping pagination."
                )
                break

            # Move backward by one day from the earliest candle.
            next_end = first_ts - DAY

            if next_end >= cursor_end:
                raise RuntimeError(
                    "Pagination cursor failed to move backward."
                )

            cursor_end = next_end

        candles = sorted(
            candles_by_timestamp.values(),
            key=lambda c: c.timestamp,
        )

        self._validate(candles, start, end)

        return candles

    @staticmethod
    def _validate(candles, start, end):

        if not candles:
            raise RuntimeError("No candles collected.")

        DAY = 24 * 60 * 60

        timestamps = [
            c.timestamp for c in candles
        ]

        if len(timestamps) != len(set(timestamps)):
            raise RuntimeError(
                "Duplicate timestamps remain."
            )

        gaps = []

        for previous, current in zip(
            timestamps,
            timestamps[1:],
        ):
            delta = current - previous

            if delta > 2 * DAY:
                gaps.append(
                    (previous, current, delta)
                )

        print()
        print("History validation:")
        print("  candles :", len(candles))
        print("  first   :", timestamps[0])
        print("  last    :", timestamps[-1])
        print("  gaps    :", len(gaps))

        if gaps:
            print()
            print("Large gaps:")

            for gap in gaps[:10]:
                print(" ", gap)

        if timestamps[0] > start + 3 * DAY:
            print(
                "  WARNING: earliest requested period "
                "was not returned by Delta."
            )

        if timestamps[-1] < end - 3 * DAY:
            print(
                "  WARNING: latest requested period "
                "was not returned by Delta."
            )


def main():

    print("=" * 70)
    print("DELTA PAGINATED BTC DAILY HISTORY")
    print("=" * 70)

    now = int(time.time())

    start = now - 5 * 365 * 24 * 60 * 60

    collector = DeltaDailyHistory()

    candles = collector.fetch(
        start=start,
        end=now,
    )

    print()
    print("FINAL RESULT")
    print("Daily candles:", len(candles))

    print()
    print("Backward pagination: COMPLETE")


if __name__ == "__main__":
    main()
