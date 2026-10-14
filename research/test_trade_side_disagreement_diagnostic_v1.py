import gzip
import json

from research.trade_side_disagreement_diagnostic_v1 import (
    aggressor_side, quote_side, diagnose,
)


def test_buyer_role_implies_aggressor_direction():
    assert aggressor_side("t") == "buy"
    assert aggressor_side("m") == "sell"
    assert aggressor_side("?") == "unknown"


def test_quote_test_boundaries():
    assert quote_side(101, 100, 101) == "buy"
    assert quote_side(100, 100, 101) == "sell"
    assert quote_side(100.5, 100, 101) == "ambiguous"


def test_diagnostic_identifies_stale_pretrade_quote(tmp_path):
    path = tmp_path / "sample.jsonl.gz"
    rows = [
        {"received_at": "q0", "message": {"type": "ob_l1", "ts": 1000000, "bp": "100", "ap": "101"}},
        {"received_at": "q1", "message": {"type": "ob_l1", "ts": 2000000, "bp": "96", "ap": "97"}},
        {"received_at": "t0", "message": {"type": "trades", "t": 1500000, "ts": 1550000, "p": "97", "s": 2, "r": "t"}},
    ]
    with gzip.open(path, "wt", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row) + "\n")
    result = diagnose([str(path)])
    assert result["comparable_trades"] == 1
    assert result["disagreement_count"] == 1
    mismatch = result["disagreements"][0]
    assert mismatch["pre_trade_quote_test"] == "sell"
    assert mismatch["buyer_role_implied_aggressor"] == "buy"
    assert mismatch["pre_quote_age_ms"] == 500
    assert mismatch["followup_classification"] == "next_quote_matches_trade_price"
