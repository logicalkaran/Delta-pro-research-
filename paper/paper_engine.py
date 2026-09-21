from datetime import datetime, timezone

from storage.models import PaperOrder, PaperPosition
from storage.trades import TradeStore


class PaperEngine:

    def __init__(
        self,
        symbol="BTCUSD",
        trade_store=None,
    ):
        self.symbol = symbol

        self.trade_store = (
            trade_store
            if trade_store is not None
            else TradeStore()
        )

        (
            self.orders,
            self.position,
            self._counter,
        ) = self.trade_store.load()

        if self.position is not None:
            if self.position.symbol != self.symbol:
                raise RuntimeError(
                    "Persisted position belongs to "
                    f"{self.position.symbol}, not {self.symbol}."
                )

    def submit(
        self,
        side: str,
        quantity: float,
        price: float,
        notional_inr: float,
        timestamp: int | None = None,
    ) -> PaperOrder:

        if side not in {"buy", "sell"}:
            raise ValueError(
                f"Invalid side: {side}"
            )

        if quantity <= 0:
            raise ValueError(
                "Quantity must be positive."
            )

        if price <= 0:
            raise ValueError(
                "Price must be positive."
            )

        if notional_inr <= 0:
            raise ValueError(
                "Notional must be positive."
            )

        if timestamp is None:
            timestamp = int(
                datetime.now(
                    timezone.utc
                ).timestamp()
            )

        # Validate position transition before
        # creating or persisting the order.
        if side == "buy":

            if self.position is not None:
                raise RuntimeError(
                    "Paper engine already has a position."
                )

        elif side == "sell":

            if self.position is None:
                raise RuntimeError(
                    "Cannot sell without a position."
                )

            if quantity > self.position.quantity:
                raise RuntimeError(
                    "Sell quantity exceeds position."
                )

        next_counter = self._counter + 1

        order = PaperOrder(
            order_id=f"PAPER-{next_counter:06d}",
            symbol=self.symbol,
            side=side,
            quantity=quantity,
            price=price,
            notional_inr=notional_inr,
            timestamp=timestamp,
        )

        new_position = self.position

        if side == "buy":

            new_position = PaperPosition(
                symbol=self.symbol,
                side="long",
                quantity=quantity,
                entry_price=price,
                entry_timestamp=timestamp,
            )

        elif side == "sell":

            if quantity == self.position.quantity:
                new_position = None

            else:
                new_position = PaperPosition(
                    symbol=self.position.symbol,
                    side=self.position.side,
                    quantity=(
                        self.position.quantity
                        - quantity
                    ),
                    entry_price=self.position.entry_price,
                    entry_timestamp=self.position.entry_timestamp,
                )

        new_orders = [
            *self.orders,
            order,
        ]

        # Persist first. Memory changes only after
        # durable storage succeeds.
        self.trade_store.save(
            orders=new_orders,
            position=new_position,
            counter=next_counter,
        )

        self.orders = new_orders
        self.position = new_position
        self._counter = next_counter

        return order

    def has_position(self) -> bool:
        return self.position is not None

    def position_notional(
        self,
        mark_price: float,
    ) -> float:

        if self.position is None:
            return 0.0

        return (
            self.position.quantity
            * mark_price
        )
