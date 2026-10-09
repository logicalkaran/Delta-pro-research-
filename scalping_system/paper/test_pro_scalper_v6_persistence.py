import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from paper import pro_scalper_v6_paper as paper


class TestV6PaperPersistence(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.old_runtime = paper.PAPER_RUNTIME_STATE
        self.old_out = paper.OUT
        self.old_config = paper.CONFIG
        paper.PAPER_RUNTIME_STATE = self.root / "runtime.json"
        paper.OUT = self.root / "paper.jsonl"
        paper.CONFIG = self.root / "config.json"
        paper.CONFIG.write_text(json.dumps({"maker_fill_probability": 1.0}))
        self.position = {
            "side": "LONG", "entry_px": 100.0, "entry_ts": 1000.0,
            "quantity_btc": 0.001, "entry_type": "MAKER", "paper_only": True,
        }

    def tearDown(self):
        paper.PAPER_RUNTIME_STATE = self.old_runtime
        paper.OUT = self.old_out
        paper.CONFIG = self.old_config
        self.tmp.cleanup()

    def test_position_and_rng_restore_after_restart(self):
        first = paper.Engine()
        first.pos = dict(self.position)
        first.rng.seed(77)
        first._save_runtime_state()
        expected_next = first.rng.random()

        second = paper.Engine()
        self.assertEqual(second.pos, self.position)
        self.assertEqual(second.rng.random(), expected_next)
        saved = json.loads(paper.PAPER_RUNTIME_STATE.read_text())
        self.assertIs(saved["real_orders"], False)
        self.assertIs(saved["paper_only"], True)

    def test_missing_state_recovers_last_logged_position(self):
        paper.OUT.write_text(json.dumps({"position": self.position, "real_orders": False}) + "\n")
        engine = paper.Engine()
        self.assertEqual(engine.pos, self.position)
        self.assertTrue(paper.PAPER_RUNTIME_STATE.exists())

    def test_position_recovery_scans_beyond_last_64kb(self):
        older_position = dict(self.position)
        records = [{"position": older_position, "real_orders": False}]
        records.extend({"position": older_position, "signal": {"action": "ABSTAIN"}, "padding": "x" * 4000} for _ in range(25))
        paper.OUT.write_text("\n".join(json.dumps(record) for record in records) + "\n")
        self.assertGreater(paper.OUT.stat().st_size, 65536)
        engine = paper.Engine()
        self.assertEqual(engine.pos, older_position)

    def test_partial_jsonl_tail_fails_closed(self):
        paper.OUT.write_text(json.dumps({"position": self.position}) + "\n" + '{"position":')
        with self.assertRaisesRegex(RuntimeError, "malformed/partial JSONL"):
            paper.Engine()

    def test_empty_existing_log_fails_closed(self):
        paper.OUT.write_text("")
        with self.assertRaisesRegex(RuntimeError, "log is empty"):
            paper.Engine()

    def test_non_finite_position_values_fail_validation(self):
        for field, value in (("entry_px", float("inf")), ("entry_ts", float("nan")), ("quantity_btc", float("-inf"))):
            with self.subTest(field=field):
                position = dict(self.position)
                position[field] = value
                self.assertFalse(paper._valid_position(position))

    def test_invalid_runtime_state_fails_closed(self):
        paper.PAPER_RUNTIME_STATE.write_text("{broken")
        with self.assertRaises(RuntimeError):
            paper.Engine()

    def test_runtime_state_without_paper_only_authority_fails_closed(self):
        paper.PAPER_RUNTIME_STATE.write_text(json.dumps({
            "schema": "pro_scalper_v6_runtime_state_v1",
            "paper_only": False,
            "real_orders": False,
            "position": None,
        }))
        with self.assertRaisesRegex(RuntimeError, "order-authority mismatch"):
            paper.Engine()

    def test_pending_trade_with_invalid_authority_fails_closed(self):
        paper.PAPER_RUNTIME_STATE.write_text(json.dumps({
            "schema": "pro_scalper_v6_runtime_state_v1",
            "paper_only": True,
            "real_orders": False,
            "position": None,
            "pending_trade": {
                "trade_id": "a" * 64,
                "trade": {"paper_only": False, "real_orders": False},
            },
        }))
        with self.assertRaisesRegex(RuntimeError, "pending trade order-authority mismatch"):
            paper.Engine()

    def test_pending_trade_payload_tampering_fails_closed(self):
        trade = {"paper_only": True, "real_orders": False, "net_bps": 1.0}
        paper.PAPER_RUNTIME_STATE.write_text(json.dumps({
            "schema": "pro_scalper_v6_runtime_state_v1",
            "paper_only": True,
            "real_orders": False,
            "position": None,
            "pending_trade": {"trade_id": "a" * 64, "trade": trade},
        }))
        with self.assertRaisesRegex(RuntimeError, "pending trade ID does not match"):
            paper.Engine()

    def test_exit_cost_respects_configured_floor(self):
        engine = paper.Engine()
        configured_floor = json.loads(paper.V5_CONFIG.read_text()).get("cost_floor_bps", 0.0)
        self.assertGreaterEqual(engine._cost_bps(), configured_floor)

    def test_pending_trade_survives_restart_and_flushes_once(self):
        first = paper.Engine()
        first.pos = dict(self.position)
        result = first.step({"order_book": {"best_bid": 99.8, "best_ask": 100.0}}, now=1002.0)
        self.assertIsNotNone(result["trade"])
        trade_id = first.pending_trade["trade_id"]
        self.assertIsNotNone(first.pending_trade)

        # Simulate process death after state persistence but before log append.
        second = paper.Engine()
        self.assertEqual(second.pending_trade["trade_id"], trade_id)
        self.assertTrue(second.flush_pending_trade())
        self.assertFalse(second.flush_pending_trade())
        records = [json.loads(line) for line in paper.OUT.read_text().splitlines()]
        trade_records = [r for r in records if r.get("trade_id") == trade_id]
        self.assertEqual(len(trade_records), 1)
        self.assertIsNone(json.loads(paper.PAPER_RUNTIME_STATE.read_text())["pending_trade"])

    def test_pending_trade_recovery_deduplicates_append_before_ack_crash(self):
        first = paper.Engine()
        first.pos = dict(self.position)
        first.step({"order_book": {"best_bid": 99.8, "best_ask": 100.0}}, now=1002.0)
        pending = dict(first.pending_trade)
        paper.OUT.write_text(json.dumps(pending) + "\n")
        recovered = paper.Engine()
        self.assertTrue(recovered.flush_pending_trade())
        records = [json.loads(line) for line in paper.OUT.read_text().splitlines()]
        self.assertEqual(sum(r.get("trade_id") == pending["trade_id"] for r in records), 1)

    def test_step_persists_new_paper_position(self):
        engine = paper.Engine()
        state = {"order_book": {"best_bid": 100.0, "best_ask": 100.5}}
        with patch.object(paper, "ensemble", return_value={"action": "LONG", "paper_only": True, "real_orders": False}):
            result = engine.step(state, now=1001.0)
        self.assertIsNotNone(result["position"])
        saved = json.loads(paper.PAPER_RUNTIME_STATE.read_text())
        self.assertEqual(saved["position"], result["position"])
        self.assertIs(saved["real_orders"], False)


if __name__ == "__main__":
    unittest.main()
