import unittest

from research.funding_carry_lab import (
    breakeven_funding_epochs, funding_continuation, funding_yield,
    margin_health, round_trip_friction_bps, short_liquidation_boundary,
)


class FundingCarryLabTests(unittest.TestCase):
    def test_002_percent_eight_hour_funding(self):
        result = funding_yield(0.0002)
        self.assertAlmostEqual(result["daily_simple_yield"], 0.0006)
        self.assertAlmostEqual(result["annual_simple_yield"], 0.219)
        self.assertTrue(result["short_receives_funding_when_rate_positive"])

    def test_round_trip_fee_sum(self):
        fees = round_trip_friction_bps(
            spot_fee_bps=10, perp_entry_fee_bps=2,
            perp_exit_fee_bps=2, spot_exit_fee_bps=10,
        )
        self.assertEqual(fees, 24)

    def test_breakeven_is_12_epochs_at_assumed_fees(self):
        result = breakeven_funding_epochs(
            round_trip_cost_bps=24, funding_rate_per_8h=0.0002,
        )
        self.assertEqual(result["epochs"], 12)
        self.assertEqual(result["days_at_three_epochs_per_day"], 4)

    def test_basis_convergence_reduces_cost(self):
        result = breakeven_funding_epochs(
            round_trip_cost_bps=24, funding_rate_per_8h=0.0002,
            basis_convergence_bps=4,
        )
        self.assertEqual(result["epochs"], 10)

    def test_no_positive_funding_edge(self):
        self.assertIsNone(breakeven_funding_epochs(
            round_trip_cost_bps=24, funding_rate_per_8h=0)["epochs"])
        self.assertEqual(funding_continuation([0.0001, -0.0001])["action"],
                         "REVIEW_UNWIND")

    def test_short_liquidation_approximations(self):
        expected = {1: 1.995, 2: 1.495, 3: 1.3283333333, 5: 1.195}
        for lev, multiple in expected.items():
            self.assertAlmostEqual(
                short_liquidation_boundary(lev)["estimated_liquidation_price_multiple"],
                multiple, places=6,
            )

    def test_short_margin_health_sees_isolated_margin_risk(self):
        result = margin_health(entry_price=100, mark_price=150, size_btc=1,
                               isolated_margin=50, maintenance_margin_rate=0.005)
        self.assertEqual(result["unrealized_short_pnl"], -50)
        self.assertTrue(result["can_be_liquidated"])
        self.assertTrue(result["spot_gain_does_not_auto_fund_perp_margin"])
        self.assertFalse(result["real_orders"])

    def test_invalid_empty_or_nonfinite_inputs_rejected(self):
        with self.assertRaises(ValueError):
            funding_continuation([])
        with self.assertRaises(ValueError):
            funding_yield(float("nan"))
        with self.assertRaises(ValueError):
            short_liquidation_boundary(0.5)
        with self.assertRaises(ValueError):
            round_trip_friction_bps(spot_fee_bps=-1, perp_entry_fee_bps=0,
                                    perp_exit_fee_bps=0, spot_exit_fee_bps=0)


if __name__ == "__main__":
    unittest.main()
