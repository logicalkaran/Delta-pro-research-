import unittest
from research.delta_feature_dataset_v1 import build, _latest_asof


def row(t, o, h, l, c, v=10):
    return {"time": t, "open": o, "high": h, "low": l, "close": c, "volume": v}


class FeatureDatasetTests(unittest.TestCase):
    def setUp(self):
        self.snap = {"collected_at": "1970-01-01T09:00:00+00:00", "candle_sets": {}}
        for res, step in (("1m",60),("5m",300),("1h",3600)):
            self.snap["candle_sets"][f"BTCUSD|price|{res}"] = {"candles": [row(i*step,100+i,102+i,99+i,101+i,10+i) for i in range(1, 8)]}
        self.snap["candle_sets"]["BTCUSD|mark|1m"] = {"candles": [row(i*60,100+i,102+i,99+i,101.5+i) for i in range(1,8)]}
        self.snap["candle_sets"]["BTCUSD|funding|1h"] = {"candles": [row(3600,0.01,0.01,0.01,0.01), row(7200,0.02,0.02,0.02,0.02)]}
        self.snap["candle_sets"]["BTCUSD|open_interest|1h"] = {"candles": [row(3600,100,100,100,100), row(7200,110,110,110,110)]}
        self.snap["tickers"] = [{"symbol":"BTCUSD", "close":999999}]
        self.snap["orderbooks"] = {"BTCUSD":{"result":{"buy":[{"price":1}],"sell":[{"price":1000000}]}}}

    def test_rows_built_for_three_timeframes(self):
        ds=build(self.snap)
        self.assertEqual(ds["row_count"],21)
        self.assertEqual({r["timeframe"] for r in ds["rows"]},{"1m","5m","1h"})

    def test_current_ticker_and_book_never_enter_historical_rows(self):
        ds=build(self.snap)
        self.assertTrue(all(r["close"] < 1000 for r in ds["rows"]))
        self.assertTrue(all("orderbook" not in r and "ticker" not in r for r in ds["rows"]))

    def test_target_is_next_bar_and_last_row_has_no_target(self):
        ds=build(self.snap)
        rows=[r for r in ds["rows"] if r["timeframe"]=="1m"]
        self.assertEqual(rows[0]["target_next_bar_return_bps"], (103/102-1)*10000)
        self.assertIsNone(rows[-1]["target_next_bar_return_bps"])
        self.assertIsNone(rows[-1]["target_next_bar_direction"])

    def test_auxiliary_asof_uses_close_timestamp_no_future(self):
        ds=build(self.snap)
        rows=[r for r in ds["rows"] if r["timeframe"]=="1h"]
        # At t=2h close, first hourly candle is available; second is not until 3h close.
        self.assertEqual(rows[0]["funding_rate_asof"],0.01)
        self.assertEqual(rows[0]["open_interest_asof"],100)

    def test_asof_rejects_future_observation(self):
        rows=[{"time":100,"v":1},{"time":200,"v":2}]
        self.assertEqual(_latest_asof(rows,[100,200],199)["v"],1)
        self.assertIsNone(_latest_asof(rows,[100,200],99))

    def test_incomplete_current_bars_are_excluded(self):
        self.snap["collected_at"] = "1970-01-01T02:00:00+00:00"
        ds=build(self.snap)
        # 1m candles with close times after 7200 are not complete at the snapshot cutoff.
        rows=[r for r in ds["rows"] if r["timeframe"]=="1m"]
        self.assertTrue(all(r["feature_available_ts"] <= 7200 for r in rows))

    def test_authority_and_methodology_are_research_only(self):
        ds=build(self.snap)
        self.assertFalse(ds["authority"]["real_orders"])
        self.assertIn("current order book excluded",ds["methodology"]["lookahead_controls"])


if __name__ == "__main__": unittest.main()
