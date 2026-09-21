from dataclasses import dataclass

from storage.state import StateStore


@dataclass(frozen=True)
class ValidatedSignal:
    signal_id: str
    signal_month: str
    execution_month: str
    fisher: float
    trigger: float


class SignalValidator:

    def __init__(
        self,
        state_store: StateStore | None = None,
    ):
        self.state_store = (
            state_store
            if state_store is not None
            else StateStore()
        )

    @staticmethod
    def next_month(month: str) -> str:
        year, month_number = map(
            int,
            month.split("-"),
        )

        if month_number == 12:
            return f"{year + 1:04d}-01"

        return f"{year:04d}-{month_number + 1:02d}"

    @staticmethod
    def make_signal_id(signal_month: str) -> str:
        return (
            f"btc_monthly_fisher_v1:"
            f"{signal_month}:bullish"
        )

    def validate(
        self,
        signal_month: str,
        fisher: float,
        trigger: float,
        bullish_cross: bool,
    ) -> ValidatedSignal | None:

        if not bullish_cross:
            return None

        signal_id = self.make_signal_id(
            signal_month
        )

        if self.state_store.is_signal_processed(
            signal_id
        ):
            return None

        execution_month = self.next_month(
            signal_month
        )

        return ValidatedSignal(
            signal_id=signal_id,
            signal_month=signal_month,
            execution_month=execution_month,
            fisher=fisher,
            trigger=trigger,
        )

    def mark_processed(
        self,
        signal: ValidatedSignal,
    ) -> None:

        self.state_store.mark_signal_processed(
            signal.signal_id
        )

    def is_processed(
        self,
        signal_id: str,
    ) -> bool:

        return self.state_store.is_signal_processed(
            signal_id
        )
