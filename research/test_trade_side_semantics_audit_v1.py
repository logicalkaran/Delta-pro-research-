from research.trade_side_semantics_audit_v1 import role_hypothesis, quote_hypothesis, audit
import gzip, json

def test_role_mapping_hypothesis():
    assert role_hypothesis("t") == "buy"
    assert role_hypothesis("m") == "sell"
    assert role_hypothesis("?") == "unknown"

def test_quote_classification():
    assert quote_hypothesis(101,100,101) == "buy"
    assert quote_hypothesis(100,100,101) == "sell"
    assert quote_hypothesis(100.5,100,101) == "ambiguous"
    assert quote_hypothesis(100,None,101) == "no_quote"

def test_audit_matches_latest_quote_before_trade_event_time(tmp_path):
    p=tmp_path/"sample.jsonl.gz"
    rows=[
      {"received_at":"2026-10-11T19:00:00+00:00","message":{"type":"ob_l1","ts":1000000,"bp":"100","ap":"101"}},
      {"received_at":"2026-10-11T19:00:01+00:00","message":{"type":"ob_l1","ts":3000000,"bp":"101","ap":"102"}},
      {"received_at":"2026-10-11T19:00:02+00:00","message":{"type":"trades","p":"101","s":1,"r":"t","t":2000000,"ts":2100000}},
      {"received_at":"2026-10-11T19:00:03+00:00","message":{"type":"trades","p":"100","s":2,"r":"t","t":2500000,"ts":2600000}},
      {"received_at":"2026-10-11T19:00:04+00:00","message":{"type":"trades","p":"101.5","s":3,"r":"m","t":4000000,"ts":4100000}},
    ]
    with gzip.open(p,"wt") as f:
      for row in rows: f.write(json.dumps(row)+"\n")
    result=audit([str(p)])
    assert result["valid_l1_quotes"] == 2
    assert result["valid_trades"] == 3
    assert result["comparable_role_quote_trades"] == 2
    assert result["role_quote_agree"] == 1
    assert result["role_quote_disagree"] == 1
    assert result["quote_test_counts"]["quote_ambiguous"] == 1
    assert result["examples"][0]["quote_event_ts"] == 1000000
