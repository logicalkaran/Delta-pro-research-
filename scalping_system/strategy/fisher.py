from dataclasses import dataclass
from math import log
from typing import Optional


@dataclass(frozen=True)
class Candle:
    timestamp: int
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class FisherValue:
    fisher: float
    trigger: float
    bullish_cross: bool


class MonthlyFisher:
    """
    Frozen BTC Fisher implementation.

    Source : HL2
    Length : 10
    Alpha  : 0.33
    Beta   : 0.67

    Matches the validated v9 research implementation.
    """

    def __init__(
        self,
        length: int = 10,
        alpha: float = 0.33,
        beta: float = 0.67,
    ):
        self.length = length
        self.alpha = alpha
        self.beta = beta

        self._hl2 = []

        # Previous recursive Fisher state.
        self._previous_raw = 0.0
        self._previous_fisher = 0.0

        # Trigger associated with the previous Fisher value.
        self._previous_trigger = 0.0

    def update(
        self,
        candle: Candle,
    ) -> Optional[FisherValue]:

        hl2 = (candle.high + candle.low) / 2.0

        self._hl2.append(hl2)

        if len(self._hl2) < self.length:
            return None

        window = self._hl2[-self.length:]

        lo = min(window)
        hi = max(window)

        if hi == lo:
            raw = self._previous_raw
        else:
            raw = 2.0 * (
                (hl2 - lo) / (hi - lo) - 0.5
            )

        raw = (
            self.alpha * raw
            + self.beta * self._previous_raw
        )

        raw = max(-0.999, min(0.999, raw))

        current_fisher = (
            0.5
            * log(
                (1.0 + raw)
                / (1.0 - raw)
            )
            + 0.5 * self._previous_fisher
        )

        # Current trigger is previous Fisher.
        current_trigger = self._previous_fisher

        # Exact research crossover:
        #
        # current Fisher > current trigger
        # AND
        # previous Fisher <= previous trigger
        bullish_cross = (
            current_fisher > current_trigger
            and self._previous_fisher
            <= self._previous_trigger
        )

        # Advance state AFTER calculating the signal.
        self._previous_raw = raw
        self._previous_trigger = current_trigger
        self._previous_fisher = current_fisher

        return FisherValue(
            fisher=current_fisher,
            trigger=current_trigger,
            bullish_cross=bullish_cross,
        )
