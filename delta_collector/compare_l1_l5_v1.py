import json
from pathlib import Path


RAW = Path(
    "data/raw/delta_btc_research_session_v2.jsonl"
)


def main():
    asks = {}
    bids = {}

    count = 0
    different = 0

    with RAW.open() as f:
        for line in f:
            record = json.loads(line)
            m = record.get("message", {})

            if m.get("type") != "ob_updates":
                continue

            action = m.get("action")

            if action == "snapshot":
                asks.clear()
                bids.clear()

                for p, s in m.get("a", []):
                    if int(s) > 0:
                        asks[p] = int(s)

                for p, s in m.get("b", []):
                    if int(s) > 0:
                        bids[p] = int(s)

            elif action == "update":
                for p, s in m.get("a", []):
                    s = int(s)

                    if s == 0:
                        asks.pop(p, None)
                    else:
                        asks[p] = s

                for p, s in m.get("b", []):
                    s = int(s)

                    if s == 0:
                        bids.pop(p, None)
                    else:
                        bids[p] = s

            else:
                continue

            if len(asks) < 5 or len(bids) < 5:
                continue

            sorted_asks = sorted(
                asks.items(),
                key=lambda x: float(x[0])
            )

            sorted_bids = sorted(
                bids.items(),
                key=lambda x: float(x[0]),
                reverse=True
            )

            best_ask_price, best_ask_size = sorted_asks[0]
            best_bid_price, best_bid_size = sorted_bids[0]

            l1_bid = int(best_bid_size)
            l1_ask = int(best_ask_size)

            l1_den = l1_bid + l1_ask

            if l1_den == 0:
                continue

            l1 = (
                (l1_bid - l1_ask)
                / l1_den
            )

            top5_asks = sorted_asks[:5]
            top5_bids = sorted_bids[:5]

            l5_bid = sum(
                int(size)
                for _, size in top5_bids
            )

            l5_ask = sum(
                int(size)
                for _, size in top5_asks
            )

            l5_den = l5_bid + l5_ask

            if l5_den == 0:
                continue

            l5 = (
                (l5_bid - l5_ask)
                / l5_den
            )

            count += 1

            if abs(l1 - l5) > 1e-12:
                different += 1

            if count <= 10:
                print()
                print(f"STATE {count}")
                print(f"L1 bid size : {l1_bid}")
                print(f"L1 ask size : {l1_ask}")
                print(f"L1 imbalance: {l1:+.8f}")
                print(f"L5 bid size : {l5_bid}")
                print(f"L5 ask size : {l5_ask}")
                print(f"L5 imbalance: {l5:+.8f}")

    print()
    print("=" * 60)
    print("L1 vs L5 DIAGNOSTIC")
    print("=" * 60)
    print(f"states checked : {count}")
    print(f"different      : {different}")

    if count:
        print(
            f"difference %   : "
            f"{different / count * 100:.2f}%"
        )


if __name__ == "__main__":
    main()
