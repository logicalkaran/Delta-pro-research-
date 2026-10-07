"""Optional live OKX connectivity smoke test.

The module is intentionally network-free during normal test collection.
Run with RUN_LIVE_NETWORK_TESTS=1 when external connectivity is explicitly desired.
"""
import os

if __name__ == "__main__":
    if os.getenv("RUN_LIVE_NETWORK_TESTS") != "1":
        print("OKX network test: SKIPPED (set RUN_LIVE_NETWORK_TESTS=1)")
    else:
        from data.cross_venue_collector_v43 import okx
        x = okx()
        assert x.price > 0
        print("OKX", x.price, x.bid, x.ask)
        print("CROSS-VENUE V4.3 OKX TEST: PASS")
