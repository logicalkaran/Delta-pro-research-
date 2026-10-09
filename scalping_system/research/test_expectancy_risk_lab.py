import math
import unittest

from research.expectancy_risk_lab import (
    analyze_expectancy,
    drawdown_recovery_gain,
    risk_overlay,
)


class TestExpectancyRiskLab(unittest.TestCase):
    def test_reference_expectancy_and_kelly(self):
        result = analyze_expectancy(0.45, 2.0, 0.01)
        self.assertAlmostEqual(result["net_expectancy_r_per_trade"], 0.35, places=10)
        self.assertAlmostEqual(result["kelly_risk_fraction"], 0.175, places=5)
        self.assertAlmostEqual(result["quarter_kelly_risk_fraction"], 0.04375, places=5)
        self.assertGreater(result["estimated_doubling_trades_at_assumed_distribution"], 190)
        self.assertLess(result["estimated_doubling_trades_at_assumed_distribution"], 220)
        self.assertIs(result["live_orders"], False)

    def test_costs_reduce_expectancy_and_growth(self):
        gross = analyze_expectancy(0.45, 2.0, 0.01, cost_r=0.0)
        net = analyze_expectancy(0.45, 2.0, 0.01, cost_r=0.10)
        self.assertLess(net["net_expectancy_r_per_trade"], gross["net_expectancy_r_per_trade"])
        self.assertLess(net["expected_log_growth_per_trade"], gross["expected_log_growth_per_trade"])

    def test_no_positive_log_growth_has_no_doubling_estimate(self):
        result = analyze_expectancy(0.30, 1.0, 0.01)
        self.assertLessEqual(result["expected_log_growth_per_trade"], 0)
        self.assertIsNone(result["estimated_doubling_trades_at_assumed_distribution"])
        self.assertEqual(result["kelly_risk_fraction"], 0.0)

    def test_drawdown_recovery_math(self):
        self.assertAlmostEqual(drawdown_recovery_gain(0.10), 1 / 9)
        self.assertAlmostEqual(drawdown_recovery_gain(0.50), 1.0)
        self.assertAlmostEqual(drawdown_recovery_gain(0.75), 3.0)

    def test_daily_stop_and_drawdown_multiplier(self):
        result = risk_overlay(-0.021, 0.11)
        self.assertTrue(result["daily_halt_required"])
        self.assertEqual(result["position_size_multiplier_for_future_trades"], 0.5)
        recovered_partial = risk_overlay(0.0, 0.07, previous_size_multiplier=0.5)
        self.assertEqual(recovered_partial["position_size_multiplier_for_future_trades"], 0.5)
        recovered = risk_overlay(0.0, 0.05, previous_size_multiplier=0.5)
        self.assertEqual(recovered["position_size_multiplier_for_future_trades"], 1.0)

    def test_invalid_inputs_fail_closed(self):
        for args in ((1.0, 2.0, 0.01), (0.45, 2.0, 0.0), (0.45, 2.0, 0.01, 2.0)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                analyze_expectancy(*args)
        with self.assertRaises(ValueError):
            drawdown_recovery_gain(1.0)
        with self.assertRaises(ValueError):
            risk_overlay(float("nan"), 0.0)


if __name__ == "__main__":
    unittest.main()
