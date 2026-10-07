import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from execution.delta_product import load_product, validate_market_order

def main():
    p = load_product("BTCUSD")
    assert p.product_id == 27
    assert p.symbol == "BTCUSD"
    assert p.contract_value_btc == 0.001
    assert p.tick_size == 0.5
    assert p.trading_status == "operational"
    validate_market_order(p, 1, "buy")
    print("Delta BTCUSD product validation: PASS")
    print(p)

if __name__ == "__main__":
    main()
