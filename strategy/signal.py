from dataclasses import dataclass
from datetime import datetime, timezone

from strategy.fisher import Candle, MonthlyFisher


@dataclass(frozen=True)
class MonthlySignal:
    month: str
    fisher: float
    trigger: float
    bullish_cross: bool


class FisherSignalEngine:

    def __init__(
        self,
        length: int = 10,
        alpha: float = 0.33,
        beta: float = 0.67,
    ):
        self.fisher = MonthlyFisher(
            length=length,
            alpha=alpha,
            beta=beta,
        )

    @staticmethod
    def month_string(timestamp: int) -> str:
        dt = datetime.fromtimestamp(
            timestamp,
            tz=timezone.utc,
        )
        return dt.strftime("%Y-%m")

    def process(
        self,
        candle: Candle,
    ) -> MonthlySignal | None:

        result = self.fisher.update(candle)

        if result is None:
            return None

        return MonthlySignal(
            month=self.month_string(candle.timestamp),
            fisher=result.fisher,
            trigger=result.trigger,
            bullish_cross=result.bullish_cross,
        )
