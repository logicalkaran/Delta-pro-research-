import json
import os
from dataclasses import asdict
from pathlib import Path

from storage.models import PaperOrder, PaperPosition


class TradeStore:

    def __init__(self, path="data/paper_trades.json"):
        self.path = Path(path)
        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

    def _load(self):
        if not self.path.exists():
            return {
                "orders": [],
                "position": None,
                "counter": 0,
            }

        try:
            with self.path.open(
                "r",
                encoding="utf-8",
            ) as f:
                data = json.load(f)

        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"Invalid trade state: {self.path}"
            ) from exc

        if not isinstance(data, dict):
            raise RuntimeError(
                "Trade state must be a JSON object."
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

    def load(self):
        data = self._load()

        orders = [
            PaperOrder(**item)
            for item in data.get("orders", [])
        ]

        position_data = data.get("position")

        position = None

        if position_data is not None:
            position = PaperPosition(
                **position_data
            )

        counter = int(
            data.get("counter", 0)
        )

        return orders, position, counter

    def save(
        self,
        orders,
        position,
        counter,
    ):
        data = {
            "orders": [
                asdict(order)
                for order in orders
            ],
            "position": (
                asdict(position)
                if position is not None
                else None
            ),
            "counter": counter,
        }

        self._atomic_write(data)
