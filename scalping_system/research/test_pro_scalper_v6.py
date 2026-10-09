import json,time,unittest,tempfile
from pathlib import Path
from unittest.mock import patch
from research import pro_scalper_v6 as v6
from research.pro_scalper_v6 import empirical_edge,empirical_edges,news_state,modeled_round_trip_cost
def test_no_future_labels():
    r=empirical_edge({"imb5":0,"imb10":0,"delta5":0,"delta30":0,"delta60":0,"ret5":0,"ret30":0,"ret60":0,"cvd_slope30":0,"spread_bps":0},0)
    assert r["ready"] is False
def test_news_is_stale_fail_closed():
    n=news_state(time.time())
    assert n["usable"] is False


class TestRoundTripCostFloor(unittest.TestCase):
    def test_floor_applies_when_component_sum_is_lower(self):
        cfg={"venue":{"effective_maker_bps":2.36,"effective_taker_bps":5.90},"taker_slippage_bps":1.0,"maker_adverse_selection_bps":1.5,"cost_floor_bps":16.0}
        self.assertAlmostEqual(modeled_round_trip_cost(cfg,0.06),16.0)

    def test_component_sum_applies_when_above_floor(self):
        cfg={"venue":{"effective_maker_bps":2.36,"effective_taker_bps":5.90},"taker_slippage_bps":1.0,"maker_adverse_selection_bps":1.5,"cost_floor_bps":10.0}
        self.assertAlmostEqual(modeled_round_trip_cost(cfg,0.5),11.26)


class TestRowsCache(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/"labels.jsonl"
        self.old_lab=v6.LAB
        self.old_signature=v6._ROWS_CACHE_SIGNATURE
        self.old_rows=v6._ROWS_CACHE
        v6.LAB=self.path
        v6._ROWS_CACHE_SIGNATURE=None
        v6._ROWS_CACHE=[]

    def tearDown(self):
        v6.LAB=self.old_lab
        v6._ROWS_CACHE_SIGNATURE=self.old_signature
        v6._ROWS_CACHE=self.old_rows
        self.temp.cleanup()

    def test_rows_cache_reuses_unchanged_file_and_invalidates_on_change(self):
        first_row={"ts":2,"labels":{"60":{"move_bps":1}}}
        self.path.write_text(json.dumps(first_row)+chr(10),encoding="utf-8")
        first=v6.rows()
        again=v6.rows()
        self.assertIs(first,again)
        self.assertEqual([row["ts"] for row in first],[2])

        second_row={"ts":1,"labels":{"60":{"move_bps":2}}}
        self.path.write_text(json.dumps(first_row)+chr(10)+json.dumps(second_row)+chr(10),encoding="utf-8")
        refreshed=v6.rows()
        self.assertIsNot(first,refreshed)
        self.assertEqual([row["ts"] for row in refreshed],[1,2])

    def test_missing_file_cache_refreshes_when_file_appears(self):
        self.assertEqual(v6.rows(),[])
        self.path.write_text(json.dumps({"ts":1,"labels":{}})+chr(10),encoding="utf-8")
        self.assertEqual([row["ts"] for row in v6.rows()],[1])

class TestMultiHorizon(unittest.TestCase):
    def test_all_horizons_share_each_feature_distance(self):
        feat={"imb5":0,"imb10":0,"delta5":0,"delta30":0,"delta60":0,
              "ret5":0,"ret30":0,"ret60":0,"cvd_slope30":0,"spread_bps":0}
        data=[]
        for i in range(40):
            labels={str(h):{"move_bps":float(i)+h/1000} for h in (60,120,180)}
            data.append({"ts":float(i),"labels":labels,**feat})
        with patch.object(v6,"distance",wraps=v6.distance) as distance_spy:
            result=empirical_edges(feat,now_ts=10000,horizons=(60,120,180),labeled_rows=data)
        self.assertEqual(distance_spy.call_count,len(data))
        for h in (60,120,180):
            self.assertTrue(result[h]["ready"])
            self.assertEqual(result[h]["n"],40)
            self.assertAlmostEqual(result[h]["long_bps"],19.5+h/1000)
