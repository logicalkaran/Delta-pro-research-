import unittest

from execution.fill_simulator import FillModel, simulate
from research.independent_event_fill_study_v1 import (
    chronological_split, evaluate, evaluate_route, purge_training_rows,
    select_non_overlapping, thresholds,
)


def row(ts, move=12.0, future_ts=None, **features):
    return {"ts": ts, "labels": {"60": {"move_bps": move, "future_ts": future_ts or ts + 60}},
            "spread_bps": 0.5,
            "imb5": features.get("imb5", 0.9), "delta5": features.get("delta5", 0.9),
            "delta30": features.get("delta30", 0.9), "ret5": features.get("ret5", 0.1),
            "ret30": features.get("ret30", 0.1)}


class IndependentEventFillStudyTests(unittest.TestCase):
    def test_non_overlap_accepts_touching_future_boundary(self):
        rows = [row(0, future_ts=10), row(5, future_ts=15), row(10, future_ts=20)]
        selected, counts = select_non_overlapping(rows, "FLOW_PRICE_CONFIRM_LONG", 60,
                                                   thresholds(rows), 1)
        self.assertEqual([x[0] for x in selected], [0, 10])
        self.assertEqual(counts, {"raw_event_count": 3, "non_overlapping_count": 2, "skip_count": 1})

    def test_thresholds_ignore_holdout_features(self):
        data = [row(i, imb5=i / 10, delta30=i / 10, delta5=i / 10,
                    ret5=i / 100, ret30=i / 100) for i in range(100)]
        _, holdout, _ = chronological_split(data)
        for r in holdout:
            for key in ("imb5", "delta30", "delta5", "ret5", "ret30"):
                r[key] = 999999
        result = evaluate(data)
        train, _, _ = chronological_split(data)
        self.assertEqual(result["split"]["thresholds"], thresholds(train))

    def test_cost_subtraction_and_maker_expected_value(self):
        model = FillModel(maker_fill_probability=0.5)
        obs = [(float(i), float(i + 60), 20.0, row(i)) for i in range(20)]
        taker = evaluate_route(obs, "TAKER", model)
        expected_taker = simulate(20, "TAKER", model=model).net_edge_bps
        self.assertEqual(taker["conditional_on_fill"]["net_mean_bps"], expected_taker)
        maker = evaluate_route(obs, "MAKER", model)
        cond = maker["conditional_on_fill"]["net_mean_bps"]
        self.assertAlmostEqual(maker["expected_net_per_signal_bps"], cond * 0.5)
        self.assertEqual(maker["fill_count"], 10)

    def test_chronological_purge(self):
        rows = [row(1, future_ts=9), row(2, future_ts=10), row(3, future_ts=11)]
        self.assertEqual([r["ts"] for r in purge_training_rows(rows, 10, 60)], [1, 2])

    def test_deterministic_results(self):
        data = [row(i * 61) for i in range(100)]
        first = evaluate(data)
        second = evaluate(data)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
