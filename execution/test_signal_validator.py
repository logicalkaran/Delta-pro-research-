import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from storage.state import StateStore
from strategy.signal_validator import SignalValidator


def main():

    print("=" * 70)
    print("SIGNAL VALIDATOR TEST")
    print("=" * 70)

    with tempfile.TemporaryDirectory() as temp_dir:

        state_path = (
            Path(temp_dir)
            / "runtime_state.json"
        )

        validator = SignalValidator(
            state_store=StateStore(state_path)
        )

        # --------------------------------------------------------
        # 1. New signal
        # --------------------------------------------------------

        signal = validator.validate(
            signal_month="2026-08",
            fisher=-2.038883,
            trigger=-2.250932,
            bullish_cross=True,
        )

        assert signal is not None

        print()
        print("Signal ID       :", signal.signal_id)
        print("Signal month    :", signal.signal_month)
        print("Execution month :", signal.execution_month)

        assert signal.execution_month == "2026-09"
        assert not validator.is_processed(
            signal.signal_id
        )

        print(
            "Validation is side-effect free: PASS"
        )

        # --------------------------------------------------------
        # 2. Uncommitted signal remains retryable
        # --------------------------------------------------------

        retry = validator.validate(
            signal_month="2026-08",
            fisher=-2.038883,
            trigger=-2.250932,
            bullish_cross=True,
        )

        assert retry is not None

        print(
            "Rejected signal remains retryable: PASS"
        )

        # --------------------------------------------------------
        # 3. Commit
        # --------------------------------------------------------

        validator.mark_processed(signal)

        assert validator.is_processed(
            signal.signal_id
        )

        print("Signal commit: PASS")

        # --------------------------------------------------------
        # 4. Duplicate blocked
        # --------------------------------------------------------

        duplicate = validator.validate(
            signal_month="2026-08",
            fisher=-2.038883,
            trigger=-2.250932,
            bullish_cross=True,
        )

        assert duplicate is None

        print(
            "Duplicate protection after commit: PASS"
        )

        # --------------------------------------------------------
        # 5. Non-crossover rejected
        # --------------------------------------------------------

        no_cross = validator.validate(
            signal_month="2026-09",
            fisher=1.0,
            trigger=0.5,
            bullish_cross=False,
        )

        assert no_cross is None

        print(
            "Non-crossover rejection: PASS"
        )

    print()
    print("Signal validator: PASS")


if __name__ == "__main__":
    main()
