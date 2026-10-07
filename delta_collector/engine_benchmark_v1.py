import json
import time
import statistics
from pathlib import Path

from delta_collector.orderbook_engine_v1 import OrderBookEngine

RAW = Path(
    "data/raw/research_sessions/"
    "btc_research_20260922_104858.jsonl"
)


def percentile(values, p):
    if not values:
        return 0.0

    values = sorted(values)
    index = int((len(values) - 1) * p / 100)
    return values[index]


def main():
    print("=" * 70)
    print("BTC ENGINE BENCHMARK V1")
    print("=" * 70)
    print(f"Input: {RAW}")

    if not RAW.exists():
        print("ERROR: input file not found")
        return

    parse_times = []
    book_times = []
    trade_times = []

    messages = 0
    trades = 0
    books = 0
    errors = 0

    orderbook = OrderBookEngine()

    start = time.perf_counter_ns()

    with RAW.open() as f:
        for line in f:
            if not line.strip():
                continue

            t0 = time.perf_counter_ns()

            try:
                record = json.loads(line)
            except Exception:
                errors += 1
                continue

            t1 = time.perf_counter_ns()

            message = record.get("message")

            if not isinstance(message, dict):
                continue

            messages += 1

            parse_times.append(t1 - t0)

            message_type = message.get("type")

            if message_type == "ob_updates":

                t2 = time.perf_counter_ns()

                try:
                    action = message.get("action")

                    if action == "snapshot":
                        orderbook.apply_snapshot(message)

                    elif action == "update":
                        orderbook.apply_update(message)

                    books += 1

                except Exception:
                    errors += 1

                t3 = time.perf_counter_ns()
                book_times.append(t3 - t2)

            elif message_type == "trades":

                t2 = time.perf_counter_ns()

                try:
                    float(message["t"])
                    float(message["p"])
                    float(message["s"])
                    trades += 1

                except Exception:
                    errors += 1

                t3 = time.perf_counter_ns()
                trade_times.append(t3 - t2)

    end = time.perf_counter_ns()

    total_ns = end - start
    total_s = total_ns / 1_000_000_000

    def report(name, values):
        if not values:
            print(f"{name}: no samples")
            return

        print()
        print(name)
        print(f"  N       : {len(values)}")
        print(f"  mean    : {statistics.mean(values) / 1000:.2f} us")
        print(f"  median  : {statistics.median(values) / 1000:.2f} us")
        print(f"  p95     : {percentile(values, 95) / 1000:.2f} us")
        print(f"  p99     : {percentile(values, 99) / 1000:.2f} us")
        print(f"  max     : {max(values) / 1000:.2f} us")

    print()
    print("RESULTS")
    print("-" * 70)

    print(f"Messages       : {messages}")
    print(f"Trades         : {trades}")
    print(f"Book updates   : {books}")
    print(f"Errors         : {errors}")
    print(f"Total time     : {total_s:.6f} s")

    if total_s:
        print(f"Messages/sec   : {messages / total_s:.2f}")
        print(f"Trades/sec     : {trades / total_s:.2f}")
        print(f"Books/sec      : {books / total_s:.2f}")

    report("JSON PARSING", parse_times)
    report("ORDER BOOK", book_times)
    report("TRADE PROCESSING", trade_times)

    print()
    print("=" * 70)
    print("BENCHMARK COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
