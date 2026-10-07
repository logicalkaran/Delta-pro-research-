"""Delta product metadata and order-parameter validation."""
from __future__ import annotations
from dataclasses import dataclass
from execution.delta_client import DeltaPublicClient

@dataclass(frozen=True)
class DeltaProduct:
    product_id: int
    symbol: str
    contract_value_btc: float
    tick_size: float
    trading_status: str

def load_product(symbol: str = "BTCUSD", client=None) -> DeltaProduct:
    p = (client or DeltaPublicClient()).get_product(symbol)
    return DeltaProduct(
        product_id=int(p["id"]),
        symbol=str(p["symbol"]),
        contract_value_btc=float(p["contract_value"]),
        tick_size=float(p["tick_size"]),
        trading_status=str(p["trading_status"]),
    )

def validate_market_order(product: DeltaProduct, size: int, side: str):
    if product.trading_status != "operational":
        raise ValueError(f"product is not operational: {product.trading_status}")
    if size < 1:
        raise ValueError("size must be at least one contract")
    if not isinstance(size, int):
        raise TypeError("size must be an integer contract count")
    if side not in {"buy", "sell"}:
        raise ValueError("side must be buy or sell")
