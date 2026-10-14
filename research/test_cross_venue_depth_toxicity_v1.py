from research.cross_venue_depth_toxicity_v1 import VPINBuckets, depth_imbalance


def test_depth_imbalance_uses_first_five_levels():
    assert depth_imbalance([[100, 8], [99, 2]], [[101, 2], [102, 8]]) == 0.0
    assert depth_imbalance(None, [[101, 2]]) is None


def test_volume_buckets_split_large_trade_and_measure_imbalance():
    v = VPINBuckets(bucket_volume=5, rolling_buckets=2)
    v.ingest(1.0, 7.0, "BUY")
    assert v.completed_count == 1
    v.ingest(2.0, 3.0, "SELL")
    assert v.completed_count == 2
    snap = v.snapshot()
    assert snap["vpin"] == 0.6  # first bucket 1.0, second bucket 0.2
    assert snap["vpin_status"] == "OK"
    assert snap["passive_making_veto"] is False  # no 2h empirical percentile yet


def test_vpin_does_not_claim_critical_without_rolling_baseline():
    v = VPINBuckets(bucket_volume=1, rolling_buckets=2)
    v.ingest(1, 1, "BUY")
    v.ingest(2, 1, "BUY")
    assert v.snapshot()["vpin"] == 1.0
    assert v.snapshot()["vpin_rolling_2h_p90"] is None
    assert v.snapshot()["vpin_critical"] is None


def test_rolling_depth_covariance_tracks_matched_imbalance_pairs():
    from research.cross_venue_depth_toxicity_v1 import RollingDepthCovariance
    c = RollingDepthCovariance(window_s=10, max_pairs=3)
    c.add(1, -0.5, -0.4)
    c.add(2, 0.0, 0.1)
    c.add(3, 0.5, 0.6)
    snap = c.snapshot()
    assert snap["n"] == 3
    assert snap["covariance"] > 0
    assert snap["correlation"] > 0.99
    c.add(4, 0.8, 0.9)
    assert c.snapshot()["n"] == 3  # bounded memory; oldest pair removed
