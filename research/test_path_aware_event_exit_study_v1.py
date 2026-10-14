import unittest

from research.event_move_cost_break_even_v1 import chronological_split, thresholds
from research.path_aware_event_exit_study_v1 import path_metrics, select_nonoverlapping


class PathAwareStudyTests(unittest.TestCase):
    def test_excursions_and_first_sampled_touch_are_directional(self):
        tape = [(0.0, 100.0), (1.0, 100.2), (2.0, 99.7), (3.0, 100.1), (4.0, 100.5)]
        result = path_metrics(tape, [x[0] for x in tape], 0.0, 100.0, 1, 3, 0, 10, 10)
        self.assertAlmostEqual(result["mfe_bps"], 20.0)
        self.assertAlmostEqual(result["mae_bps"], -30.0)
        self.assertEqual(result["first_target_or_stop_touch"]["kind"], "target")
        self.assertEqual(result["exit_ts"], 3.0)

    def test_future_samples_after_horizon_cannot_change_metrics(self):
        base = [(0.0, 100.0), (1.0, 100.1), (2.0, 100.2), (3.0, 100.1)]
        extended = base + [(4.0, 80.0), (5.0, 120.0)]
        a = path_metrics(base, [x[0] for x in base], 0.0, 100.0, 1, 2, 0, 1000, 1000)
        b = path_metrics(extended, [x[0] for x in extended], 0.0, 100.0, 1, 2, 0, 1000, 1000)
        self.assertEqual(a, b)

    def test_delay_uses_first_sample_at_or_after_requested_time(self):
        tape = [(0.0, 100.0), (0.7, 100.1), (1.4, 100.2), (2.1, 100.3), (3.0, 100.4)]
        result = path_metrics(tape, [x[0] for x in tape], 0.0, 100.0, 1, 1, 1, 1000, 1000)
        self.assertEqual(result["entry_ts"], 1.4)
        self.assertAlmostEqual(result["entry_delay_observed_seconds"], 1.4)
        self.assertEqual(result["exit_ts"], 3.0)

    def test_selection_is_nonoverlapping_for_maximum_tested_delay(self):
        events = [(10.0, {}), (23.0, {}), (25.0, {}), (40.0, {})]
        selected = select_nonoverlapping(events, horizon=10, max_delay=5)
        self.assertEqual([ts for ts, _ in selected], [10.0, 25.0, 40.0])
        for (start, _), (next_start, _) in zip(selected, selected[1:]):
            self.assertGreaterEqual(next_start, start + 10 + 5)

    def test_path_metrics_exclude_exit_after_tested_window(self):
        tape = [(0.0, 100.0), (1.0, 100.1), (2.0, 100.2), (3.0, 100.3)]
        result = path_metrics(tape, [x[0] for x in tape], 0.0, 100.0, 1, 2, 0,
                              1000, 1000, window_end=1.5)
        self.assertIsNone(result)

    def test_holdout_mutation_does_not_change_train_thresholds(self):
        rows = [{"ts": float(i), "imb5": i, "delta30": i, "delta5": i,
                 "ret30": i, "ret5": i} for i in range(100)]
        train, holdout, _ = chronological_split(rows)
        before = thresholds(train)
        for row in holdout:
            for key in ("imb5", "delta30", "delta5", "ret30", "ret5"):
                row[key] = -1_000_000
        train_after, _, _ = chronological_split(rows)
        self.assertEqual(before, thresholds(train_after))


if __name__ == "__main__":
    unittest.main()
