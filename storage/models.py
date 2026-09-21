from dataclasses import dataclass


@dataclass(frozen=True)
class PaperOrder:
    order_id: str
    symbol: str
    side: str
    quantity: float
    price: float
    notional_inr: float
    timestamp: int


@dataclass
class PaperPosition:
    symbol: str
    side: str
    quantity: float
    entry_price: float
    entry_timestamp: int
