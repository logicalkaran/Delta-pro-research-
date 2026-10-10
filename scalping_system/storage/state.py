import json
import os
from pathlib import Path


class StateStore:

    def __init__(self, path="data/runtime_state.json"):
        self.path = Path(path)
        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

    def _load(self):
        if not self.path.exists():
            return {}

        try:
            with self.path.open(
                "r",
                encoding="utf-8",
            ) as f:
                data = json.load(f)

        except (OSError, json.JSONDecodeError):
            raise RuntimeError(
                f"Invalid state file: {self.path}"
            )

        if not isinstance(data, dict):
            raise RuntimeError(
                "State file must contain a JSON object."
            )

        return data

    def _atomic_write(self, data):
        temporary = self.path.with_suffix(
            self.path.suffix + ".tmp"
        )

        with temporary.open(
            "w",
            encoding="utf-8",
        ) as f:
            json.dump(
                data,
                f,
                indent=2,
                sort_keys=True,
            )
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())

        os.replace(
            temporary,
            self.path,
        )

    def get_processed_signals(self):
        data = self._load()

        signals = data.get(
            "processed_signals",
            [],
        )

        if not isinstance(signals, list):
            raise RuntimeError(
                "processed_signals must be a list."
            )

        return set(signals)

    def mark_signal_processed(
        self,
        signal_id: str,
    ):
        if not signal_id:
            raise ValueError(
                "signal_id cannot be empty."
            )

        data = self._load()

        signals = data.setdefault(
            "processed_signals",
            [],
        )

        if signal_id not in signals:
            signals.append(signal_id)

        self._atomic_write(data)

    def is_signal_processed(
        self,
        signal_id: str,
    ) -> bool:
        return signal_id in (
            self.get_processed_signals()
        )
