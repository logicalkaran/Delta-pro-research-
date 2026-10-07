"""Optional public cross-venue connectivity smoke test.

Normal pytest collection is network-free. Set RUN_LIVE_NETWORK_TESTS=1 to run it.
"""
import os

if __name__ == "__main__":
    if os.getenv("RUN_LIVE_NETWORK_TESTS") != "1":
        print("Cross-venue network test: SKIPPED (set RUN_LIVE_NETWORK_TESTS=1)")
    else:
        from data.cross_venue_collector_v43 import binance, bybit, delta
        for fn in (binance, bybit, delta):
            x=fn()
            assert x.price>0
            print(x.venue,x.price)
        print("CROSS-VENUE V4.3 PUBLIC FEED TEST: PASS")
