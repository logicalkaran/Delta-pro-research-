"""Read-only diagnostic for trade-role vs pre-trade L1 quote disagreements.

Delta's compact public trades feed documents r as buyer_role: t=taker, m=maker.
A buyer taker implies buy aggression; a buyer maker implies sell aggression.
The L1 quote test is only a timing-sensitive proxy, not ground truth.
"""
import argparse
import bisect
import gzip
import glob
import json
import os


def aggressor_side(buyer_role):
    return {"t": "buy", "m": "sell"}.get(buyer_role, "unknown")


def quote_side(price, bid, ask):
    if bid <= 0 or ask <= 0 or bid > ask:
        return "no_quote"
    if price >= ask:
        return "buy"
    if price <= bid:
        return "sell"
    return "ambiguous"


def load_events(paths):
    quotes, trades = [], []
    malformed = 0
    for path in paths:
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            for line in stream:
                try:
                    row = json.loads(line)
                    msg = row.get("message") or {}
                    if msg.get("type") == "ob_l1":
                        try:
                            q = {
                                "ts": int(msg["ts"]),
                                "bid": float(msg["bp"]),
                                "ask": float(msg["ap"]),
                                "received_at": row.get("received_at"),
                                "lts": msg.get("lts"),
                            }
                            if 0 < q["bid"] <= q["ask"]:
                                quotes.append(q)
                        except (KeyError, TypeError, ValueError):
                            pass
                    elif msg.get("type") == "trades":
                        try:
                            trades.append({
                                "event_ts": int(msg["t"]),
                                "publish_ts": int(msg["ts"]),
                                "price": float(msg["p"]),
                                "size": abs(float(msg["s"])),
                                "buyer_role": msg.get("r"),
                                "received_at": row.get("received_at"),
                            })
                        except (KeyError, TypeError, ValueError):
                            pass
                except (json.JSONDecodeError, TypeError):
                    malformed += 1
    return quotes, trades, malformed


def diagnose(paths):
    quotes, trades, malformed = load_events(paths)
    quotes.sort(key=lambda q: q["ts"])
    trades.sort(key=lambda t: t["event_ts"])
    qts = [q["ts"] for q in quotes]
    mismatches = []
    comparable = agree = 0
    for trade in trades:
        idx = bisect.bisect_right(qts, trade["event_ts"]) - 1
        if idx < 0:
            continue
        before = quotes[idx]
        role_side = aggressor_side(trade["buyer_role"])
        test_side = quote_side(trade["price"], before["bid"], before["ask"])
        if role_side not in ("buy", "sell") or test_side not in ("buy", "sell"):
            continue
        comparable += 1
        if role_side == test_side:
            agree += 1
            continue
        next_idx = bisect.bisect_right(qts, trade["event_ts"])
        after = quotes[next_idx] if next_idx < len(quotes) else None
        after_ms = (after["ts"] - trade["event_ts"]) / 1000 if after else None
        if after and (trade["price"] == after["bid"] or trade["price"] == after["ask"]):
            followup = "next_quote_matches_trade_price"
        else:
            followup = "no_immediate_quote_price_match"
        mismatches.append({
            "trade": trade,
            "buyer_role_implied_aggressor": role_side,
            "pre_trade_quote_test": test_side,
            "pre_trade_quote": before,
            "pre_quote_age_ms": (trade["event_ts"] - before["ts"]) / 1000,
            "next_quote": after,
            "next_quote_delay_ms": after_ms,
            "followup_classification": followup,
        })
    return {
        "schema": "trade_side_disagreement_diagnostic_v1",
        "inputs": paths,
        "valid_l1_quotes": len(quotes),
        "valid_trades": len(trades),
        "malformed_json": malformed,
        "comparable_trades": comparable,
        "agreement_count": agree,
        "disagreement_count": len(mismatches),
        "agreement_rate": agree / comparable if comparable else None,
        "disagreements": mismatches,
        "limitations": [
            "Delta documents r as buyer_role (t= taker, m=maker); inferred aggressor side is not a separate side field.",
            "The pre-trade L1 quote test can disagree when quotes are asynchronous or stale relative to trade events.",
            "A subsequent quote matching trade price is diagnostic evidence of repricing, not proof of causality or trade direction.",
            "Research-only; no production strategy or execution settings are changed."
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*")
    parser.add_argument("--output", default="data/processed/trade_side_disagreement_diagnostic_v1.json")
    args = parser.parse_args()
    paths = args.paths or sorted(glob.glob(
        "data/raw/quant_protocol_bounded/**/*_raw/**/*.jsonl.gz", recursive=True
    ))
    if not paths:
        raise SystemExit("No raw capture files found")
    result = diagnose(paths)
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps({k: v for k, v in result.items() if k not in ("inputs", "disagreements")}, indent=2))
    print("output:", args.output)


if __name__ == "__main__":
    main()
