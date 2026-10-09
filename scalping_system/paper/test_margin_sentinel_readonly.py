import unittest
from decimal import Decimal

from paper.margin_sentinel_readonly import evaluate_position, evaluate_snapshot, extract_positions


class MarginSentinelReadOnlyTests(unittest.TestCase):
    def base(self, **updates):
        pos = {
            "product_symbol": "BTCUSD",
            "size": "1",
            "side": "long",
            "margin_mode": "isolated",
            "mark_price": "100",
            "liquidation_price": "90",
            "margin": "100",
            "maintenance_margin": "10",
            "unrealized_pnl": "0",
        }
        pos.update(updates)
        return pos

    def test_healthy_position_no_action(self):
        result = evaluate_position(self.base())
        self.assertEqual(result["status"], "OK")
        self.assertEqual(result["action"], "ALERT_ONLY_NO_COLLATERAL_TRANSFER")
        self.assertFalse(result["real_orders"])

    def test_utilization_threshold_alert(self):
        result = evaluate_position(self.base(margin="10", maintenance_margin="8"))
        self.assertEqual(result["status"], "ALERT")
        self.assertIn("MARGIN_UTILIZATION_THRESHOLD", result["reasons"])

    def test_liquidation_distance_threshold_alert(self):
        result = evaluate_position(self.base(mark_price="100", liquidation_price="96"))
        self.assertIn("LIQUIDATION_DISTANCE_THRESHOLD", result["reasons"])

    def test_long_wrong_side_of_liquidation(self):
        result = evaluate_position(self.base(mark_price="89", liquidation_price="90"))
        self.assertIn("MARK_AT_OR_BEYOND_LIQUIDATION_ESTIMATE", result["reasons"])

    def test_short_wrong_side_of_liquidation(self):
        result = evaluate_position(self.base(side="short", mark_price="111", liquidation_price="110"))
        self.assertIn("MARK_AT_OR_BEYOND_LIQUIDATION_ESTIMATE", result["reasons"])

    def test_wrong_symbol_ignored(self):
        result = evaluate_position(self.base(product_symbol="ETHUSDT"))
        self.assertEqual(result["status"], "IGNORED_SYMBOL")

    def test_cross_margin_not_managed(self):
        result = evaluate_position(self.base(margin_mode="cross"))
        self.assertEqual(result["status"], "REVIEW_MARGIN_MODE")

    def test_bad_metrics_fail_closed(self):
        with self.assertRaises(ValueError):
            evaluate_position(self.base(mark_price="NaN"))
        with self.assertRaises(ValueError):
            evaluate_position(self.base(mark_price="0"))

    def test_snapshot_formats(self):
        positions = [self.base()]
        self.assertEqual(len(extract_positions({"result": positions})), 1)
        self.assertEqual(len(evaluate_snapshot(positions)), 1)
        with self.assertRaises(ValueError):
            extract_positions({"result": "not-a-list"})

    def test_no_network_or_mutation_capability(self):
        import inspect
        import paper.margin_sentinel_readonly as module
        source = inspect.getsource(module)
        self.assertNotIn("requests.", source)
        self.assertNotIn("change_margin", source)
        self.assertNotIn("api_secret", source)


if __name__ == "__main__":
    unittest.main()
