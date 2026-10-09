import time
from typing import Any

import requests


class DeltaPublicClient:
    """
    Read-only Delta India market-data client.

    No API key.
    No private endpoints.
    No order placement.
    """

    BASE_URL = "https://api.india.delta.exchange"

    def __init__(
        self,
        base_url: str = BASE_URL,
        timeout: float = 15.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> Any:

        url = f"{self.base_url}{path}"

        response = requests.get(
            url,
            params=params,
            timeout=self.timeout,
            headers={
                "User-Agent": "btc-fisher-trader/1.0",
                "Accept": "application/json",
            },
        )

        response.raise_for_status()

        payload = response.json()

        if isinstance(payload, dict):
            if payload.get("success") is False:
                raise RuntimeError(
                    f"Delta API error: {payload}"
                )

        return payload

    def get_products(self):
        return self._get("/v2/products")

    def get_product(self, symbol: str):
        products = self.get_products()

        results = products.get("result", [])

        for product in results:
            if product.get("symbol") == symbol:
                return product

        raise ValueError(
            f"Delta product not found: {symbol}"
        )

    def get_candles(
        self,
        symbol: str,
        resolution: str,
        start: int,
        end: int,
    ):
        """
        Fetch OHLC candles.

        start/end are Unix timestamps in seconds.
        """

        return self._get(
            "/v2/history/candles",
            params={
                "symbol": symbol,
                "resolution": resolution,
                "start": start,
                "end": end,
            },
        )


def main():

    client = DeltaPublicClient()

    print("=" * 70)
    print("DELTA PUBLIC MARKET DATA TEST")
    print("=" * 70)

    print()
    print("Testing product endpoint...")

    products = client.get_products()

    if not isinstance(products, dict):
        raise RuntimeError(
            "Unexpected products response"
        )

    results = products.get("result", [])

    print(
        f"Products returned: {len(results)}"
    )

    print()
    print("Searching BTC...")

    btc = [
        p for p in results
        if "BTC" in str(p.get("symbol", "")).upper()
    ]

    for p in btc[:10]:
        print(
            p.get("symbol"),
            "| contract_type=",
            p.get("contract_type"),
            "| settle=",
            p.get("settling_asset"),
        )

    print()
    print("Public API connectivity: PASS")


if __name__ == "__main__":
    main()
