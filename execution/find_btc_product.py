from delta_client import DeltaPublicClient


def main():
    client = DeltaPublicClient()

    products = client.get_products().get("result", [])

    print("=" * 70)
    print("BTC PERPETUAL PRODUCT DISCOVERY")
    print("=" * 70)

    matches = []

    for p in products:
        symbol = str(p.get("symbol", "")).upper()
        contract_type = str(p.get("contract_type", "")).lower()

        if "BTC" not in symbol:
            continue

        if "perpetual" not in contract_type:
            continue

        matches.append(p)

    if not matches:
        print("ERROR: No BTC perpetual product found.")
        raise SystemExit(1)

    for p in matches:
        print()
        print("Symbol       :", p.get("symbol"))
        print("Product ID   :", p.get("id"))
        print("Contract     :", p.get("contract_type"))
        print("Underlying   :", p.get("underlying_asset"))
        print("Settlement   :", p.get("settling_asset"))
        print("Tick size    :", p.get("tick_size"))
        print("Lot size     :", p.get("contract_value"))
        print("Min quantity :", p.get("min_order_size"))
        print("Status       :", p.get("state"))

    print()
    print("BTC perpetual candidates:", len(matches))


if __name__ == "__main__":
    main()
