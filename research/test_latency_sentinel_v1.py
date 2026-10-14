from research.latency_sentinel_v1 import assess_latency


def test_latency_over_50ms_rejected():
    result = assess_latency(50.1, 100)
    assert not result.eligible_for_paper_evaluation
    assert result.reason == "ROUND_TRIP_LATENCY_TOO_HIGH"


def test_stale_market_rejected_even_with_fast_rtt():
    result = assess_latency(10, 2001)
    assert not result.eligible_for_paper_evaluation
    assert result.reason == "MARKET_DATA_STALE"


def test_missing_and_negative_metrics_fail_closed():
    assert not assess_latency(None, 10).eligible_for_paper_evaluation
    assert not assess_latency(-1, 10).eligible_for_paper_evaluation


def test_good_metrics_only_eligible_for_paper():
    result = assess_latency(20, 100)
    assert result.eligible_for_paper_evaluation
    assert result.reason == "LATENCY_OK_FOR_PAPER_ONLY"
