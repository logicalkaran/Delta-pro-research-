import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from storage.state import StateStore
from strategy.signal_validator import SignalValidator


def main():

    print("=" * 70)
    print("PERSISTENT SIGNAL STATE TEST")
    print("=" * 70)

    with tempfile.TemporaryDirectory() as temp_dir:

        state_path = (
            Path(temp_dir)
            / "runtime_state.json"
        )

        # --------------------------------------------------------
        # Validator instance #1
        # --------------------------------------------------------

        store1 = StateStore(state_path)

        validator1 = SignalValidator(
            state_store=store1
        )

        signal = validator1.validate(
            signal_month="2026-08",
            fisher=-2.038883,
            trigger=-2.250932,
            bullish_cross=True,
        )

        assert signal is not None

        print()
        print(
            "Initial validation: PASS"
        )

        # Not committed yet.
        assert not validator1.is_processed(
            signal.signal_id
        )

        retry = validator1.validate(
            signal_month="2026-08",
            fisher=-2.038883,
            trigger=-2.250932,
            bullish_cross=True,
        )

        assert retry is not None

        print(
            "Rejected/uncommitted signal remains retryable: PASS"
        )

        # --------------------------------------------------------
        # Commit after downstream acceptance.
        # --------------------------------------------------------

        validator1.mark_processed(signal)

        assert validator1.is_processed(
            signal.signal_id
        )

        print(
            "Persistent commit: PASS"
        )

        # --------------------------------------------------------
        # Simulate process restart.
        # --------------------------------------------------------

        store2 = StateStore(state_path)

        validator2 = SignalValidator(
            state_store=store2
        )

        duplicate = validator2.validate(
            signal_month="2026-08",
            fisher=-2.038883,
            trigger=-2.250932,
            bullish_cross=True,
        )

        assert duplicate is None

        print(
            "Duplicate blocked after restart: PASS"
        )

        print()
        print(
            "Persistent signal state: PASS"
        )


if __name__ == "__main__":
    main()
