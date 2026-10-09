import json
import tempfile
import unittest
from pathlib import Path
from research.qwen_specialization.layer import build_training, make_example, timeframe_context, build_context

class SpecializationLayerTests(unittest.TestCase):
    def test_future_outcomes_are_only_targets(self):
        row={"ts":100,"mid":10,"imb5":0.2,"labels":{"60":{"future_ts":160,"future_mid":11,"move_bps":100}}}
        ex=make_example(row,True)
        encoded=json.dumps(ex)
        self.assertNotIn("labels",json.dumps(ex["input"]))
        self.assertNotIn("future_mid",encoded)
        self.assertNotIn("future_ts",encoded)
        self.assertEqual(ex["target"]["horizons"]["60"]["move_bps"],100)

    def test_builder_limits_and_preserves_separate_targets(self):
        with tempfile.TemporaryDirectory() as td:
            d=Path(td); f=d/"f.jsonl"; l=d/"l.jsonl"; o=d/"out.jsonl"
            f.write_text("".join(json.dumps({"ts":i,"mid":10,"imb5":0.1})+"\n" for i in range(5)))
            l.write_text("".join(json.dumps({"ts":i,"mid":10,"imb5":0.1,"labels":{"60":{"move_bps":i}}})+"\n" for i in range(3)))
            stats=build_training(f,l,o,feature_limit=4,label_limit=2)
            rows=[json.loads(x) for x in o.read_text().splitlines()]
            self.assertEqual((stats["feature_snapshots"],stats["labeled_examples"]),(4,2))
            self.assertTrue(all("target" not in r for r in rows[:4]))
            self.assertTrue(all("labels" not in r["input"] for r in rows))

    def test_timeframes_require_full_closed_window(self):
        cs=[{"timestamp":i*60,"open":i+1,"high":i+2,"low":i,"close":i+1,"volume":1} for i in range(20)]
        ctx=timeframe_context(cs)
        self.assertTrue(ctx["5m"]["ready"])
        self.assertTrue(ctx["15m"]["ready"])
        self.assertFalse(ctx["1h"]["ready"])

    def test_context_never_retrieves_labeled_tape(self):
        with tempfile.TemporaryDirectory() as td:
            d=Path(td); state=d/"s.json"; candles=d/"c.json"; tape=d/"t.jsonl"
            state.write_text(json.dumps({"updated_at_epoch":100,"order_book":{"mid_price":10,"best_bid":9.9,"best_ask":10.1}}))
            candles.write_text(json.dumps([]))
            tape.write_text(json.dumps({"ts":99,"mid":10,"imb5":0.1,"labels":{"60":{"move_bps":999}}})+"\n")
            result=build_context(state,candles,now_ts=101,tape_path=tape)
            self.assertNotIn("move_bps",json.dumps(result))
            self.assertNotIn("future_ts",json.dumps(result))
            self.assertEqual(result["micro_age_seconds"],1)
            self.assertEqual(result["timeframes"]["5m"]["ready"],False)

if __name__=="__main__": unittest.main()
