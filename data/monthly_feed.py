from datetime import datetime, timezone

from strategy.fisher import Candle
from data.market_state import aggregate_daily_to_monthly


class MonthlyMarketFeed:

    def __init__(self, daily_candles: list[Candle]):
        self.daily_candles = sorted(
            daily_candles,
            key=lambda c: c.timestamp,
        )

    @staticmethod
    def _month_key(timestamp: int) -> tuple[int, int]:
        dt = datetime.fromtimestamp(
            timestamp,
            tz=timezone.utc,
        )
        return dt.year, dt.month

    @staticmethod
    def _current_month() -> tuple[int, int]:
        now = datetime.now(timezone.utc)
        return now.year, now.month

    def monthly_candles(self) -> list[Candle]:
        return aggregate_daily_to_monthly(
            self.daily_candles
        )

    def completed_months(self) -> list[Candle]:

        current_year, current_month = (
            self._current_month()
        )

        return [
            candle
            for candle in self.monthly_candles()
            if self._month_key(candle.timestamp)
            != (current_year, current_month)
        ]

    def incomplete_month(self) -> Candle | None:

        current_year, current_month = (
            self._current_month()
        )

        for candle in self.monthly_candles():

            if self._month_key(candle.timestamp) == (
                current_year,
                current_month,
            ):
                return candle

        return None
