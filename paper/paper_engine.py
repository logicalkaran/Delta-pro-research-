from datetime import datetime, timezone

from storage.models import PaperOrder, PaperPosition
from storage.trades import TradeStore


class PaperEngine:
    """Persistent, exchange-free paper position engine.

    buy with no position opens LONG; sell with no position opens SHORT.
    The opposite side closes the existing position. No live API is called.
    """

    def __init__(self, symbol="BTCUSD", trade_store=None):
        self.symbol = symbol
        self.trade_store = trade_store if trade_store is not None else TradeStore()
        self.orders, self.position, self._counter = self.trade_store.load()
        if self.position is not None and self.position.symbol != self.symbol:
            raise RuntimeError(f"Persisted position belongs to {self.position.symbol}, not {self.symbol}.")
        if self.position is not None and self.position.side not in {"long", "short"}:
            raise RuntimeError(f"Invalid persisted position side: {self.position.side}")

    def submit(self, side: str, quantity: float, price: float, notional_inr: float, timestamp: int | None = None) -> PaperOrder:
        if side not in {"buy", "sell"}:
            raise ValueError(f"Invalid side: {side}")
        if quantity <= 0:
            raise ValueError("Quantity must be positive.")
        if price <= 0:
            raise ValueError("Price must be positive.")
        if notional_inr <= 0:
            raise ValueError("Notional must be positive.")
        if timestamp is None:
            timestamp = int(datetime.now(timezone.utc).timestamp())

        next_counter = self._counter + 1
        order = PaperOrder(
            order_id=f"PAPER-{next_counter:06d}", symbol=self.symbol,
            side=side, quantity=quantity, price=price,
            notional_inr=notional_inr, timestamp=timestamp,
        )

        new_position = self._transition(side, quantity, price, timestamp)
        new_orders = [*self.orders, order]
        self.trade_store.save(orders=new_orders, position=new_position, counter=next_counter)
        self.orders, self.position, self._counter = new_orders, new_position, next_counter
        return order

    def _transition(self, side, quantity, price, timestamp):
        if self.position is None:
            return PaperPosition(
                symbol=self.symbol,
                side="long" if side == "buy" else "short",
                quantity=quantity,
                entry_price=price,
                entry_timestamp=timestamp,
            )

        closing_side = "sell" if self.position.side == "long" else "buy"
        if side != closing_side:
            raise RuntimeError("Same-direction position already exists; reversal requires an explicit close first.")
        if quantity > self.position.quantity:
            raise RuntimeError("Close quantity exceeds position.")
        if quantity == self.position.quantity:
            return None
        return PaperPosition(
            symbol=self.position.symbol,
            side=self.position.side,
            quantity=self.position.quantity - quantity,
            entry_price=self.position.entry_price,
            entry_timestamp=self.position.entry_timestamp,
        )

    def has_position(self) -> bool:
        return self.position is not None

    def position_notional(self, mark_price: float) -> float:
        if self.position is None:
            return 0.0
        return self.position.quantity * mark_price

    def unrealized_pnl(self, mark_price: float) -> float:
        if self.position is None:
            return 0.0
        delta = mark_price - self.position.entry_price
        if self.position.side == "short":
            delta = -delta
        return self.position.quantity * delta
