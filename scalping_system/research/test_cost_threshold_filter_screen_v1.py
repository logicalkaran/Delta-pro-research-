import unittest
from research.cost_threshold_filter_screen_v1 import direction, gross_outcome, split_for

class TestCostThresholdFilterScreen(unittest.TestCase):
    def test_fixed_target_and_stop_do_not_use_sampled_overshoot(self):
        self.assertEqual(gross_outcome({"class": "TARGET_FIRST", "terminal_move_bps": 38.0}), 20.0)
        self.assertEqual(gross_outcome({"class": "STOP_FIRST", "terminal_move_bps": -17.0}), -10.0)

    def test_timeout_uses_observed_terminal_mid_return(self):
        self.assertAlmostEqual(gross_outcome({"class": "ABSTAIN_NO_BARRIER", "terminal_move_bps": 4.2}), 4.2)

    def test_confluence_requires_minimum_directional_votes(self):
        row = {"delta30": 1.0, "ret30": 1.0, "imb10": -1.0, "cvd": 0.0, "regime": "NEUTRAL"}
        self.assertEqual(direction(row, "confluence2of4"), 0)
        row["cvd"] = 1.0
        self.assertEqual(direction(row, "confluence2of4"), 1)
        self.assertEqual(direction(row, "confluence3of4"), 0)
        row["imb10"] = 1.0
        self.assertEqual(direction(row, "confluence3of4"), 1)

    def test_chronological_split_purges_boundaries(self):
        self.assertEqual(split_for(100.0, 1000.0, 2000.0), "train")
        self.assertIsNone(split_for(1000.0, 1000.0, 2000.0))
        self.assertEqual(split_for(1500.0, 1000.0, 2000.0), "validation")
        self.assertEqual(split_for(3000.0, 1000.0, 2000.0), "test")

if __name__ == "__main__":
    unittest.main()
