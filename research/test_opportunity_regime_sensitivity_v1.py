import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from opportunity_regime_sensitivity_v1 import analyze, settings, threshold_state, _net


def row(ts, *, ret5=0.0002, ret30=0.0004, ret60=0.0006, delta5=1, delta30=1, move=20, future=None, spread=0.5):
    return {"ts": ts, "ret5": ret5, "ret30": ret30, "ret60": ret60, "delta5": delta5, "delta30": delta30,
            "spread_bps": spread, "labels": {"60": {"move_bps": move, "future_ts": ts + 60 if future is None else future}}}


class SensitivityTests(unittest.TestCase):
    def test_percentage_point_conversion_and_threshold_sensitivity(self):
        # 0.0006 percentage points -> 0.000006 decimal -> 0.06 bps.
        r = row(1, ret5=0.0002, ret30=0.0004, ret60=0.0006, delta5=-1, delta30=-1)
        low = {"volatility_bps": .05, "divergence_bps": .03, "toxicity_bps": .01, "trend_bps": .03}
        high = {"volatility_bps": .1, "divergence_bps": .03, "toxicity_bps": .01, "trend_bps": .03}
        self.assertEqual(threshold_state(r, low)[0], "high_vol")
        self.assertEqual(threshold_state(r, high)[0], "low_vol")
        self.assertEqual(len(settings()), 108)

    def test_cost_subtracts_fee_and_two_observed_spreads(self):
        r = row(10, move=20, spread=.5)
        self.assertAlmostEqual(_net(r, "60", 1, 11.8), 7.2)

    def test_chronological_split_and_horizon_purge(self):
        rows = [row(i * 100, future=i * 100 + (300 if i == 5 else 60)) for i in range(50)]
        report = analyze(rows)
        self.assertEqual(report["split"]["train"]["rows"], 30)
        self.assertEqual(report["split"]["holdout"]["rows"], 20)
        self.assertEqual(report["split"]["holdout_start_ts"], 3000)
        # The row at 500 is purged for the 60s label because future_ts exceeds boundary.
        self.assertIn("future_ts", report["split"]["purge"])

    def test_holdout_outcomes_never_change_selection(self):
        rows = [row(i * 100, move=(10 if i < 30 else 10000), future=i * 100 + 60) for i in range(50)]
        before = analyze(rows)
        mutated = copy.deepcopy(rows)
        for r in mutated[30:]:
            r["labels"]["60"]["move_bps"] *= -1000
        after = analyze(mutated)
        selected_before = [(c["setting"], c["state"], c["horizon_seconds"], c["direction"], c["train"]) for c in before["candidates_selected_using_training_only"]]
        selected_after = [(c["setting"], c["state"], c["horizon_seconds"], c["direction"], c["train"]) for c in after["candidates_selected_using_training_only"]]
        self.assertEqual(selected_before, selected_after)


if __name__ == "__main__":
    unittest.main()
