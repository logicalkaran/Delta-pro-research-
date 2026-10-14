import unittest

from execution.fill_simulator import FillModel, simulate
from research.event_move_cost_break_even_v1 import (
    chronological_split, evaluate, purge_training_rows, select_non_overlapping,
    thresholds,
)


def row(ts, move=20.0, future_ts=None, spread_bps=0.5, **features):
    return {"ts": float(ts), "spread_bps": spread_bps, "regime": "TEST",
            "imb5": features.get("imb5", 0.9), "delta5": features.get("delta5", 0.9),
            "delta30": features.get("delta30", 0.9), "ret5": features.get("ret5", 0.1),
            "ret30": features.get("ret30", 0.1),
            "labels": {str(h): {"move_bps": move, "future_ts": future_ts or ts + h}
                       for h in (60, 120, 180, 300)}}


class EventMoveCostBreakEvenTests(unittest.TestCase):
    def test_cost_math_matches_fill_simulator_and_spread_fee_diagnostic(self):
        data = [row(i * 400, move=20) for i in range(80)]
        report = evaluate(data)
        holdout_rows = report["split"]["holdout_rows"]
        self.assertEqual(holdout_rows, 32)
        taker_cost = simulate(0, "TAKER", FillModel()).total_cost_bps
        self.assertEqual(taker_cost, 15.8)
        # Inspect cost math directly through one eligible summary in synthetic data.
        result = next(x for x in report["results"] if x["route"] == "TAKER")
        m = result["metrics"]
        self.assertEqual(m["gross_mean_conditional_on_fill_bps"], 20)
        self.assertAlmostEqual(m["full_cost"]["conditional_net_mean_bps"], 20 - taker_cost)
        self.assertAlmostEqual(m["full_cost"]["expected_net_per_signal_bps"], 20 - taker_cost)
        self.assertAlmostEqual(m["observed_spread_fees_only"]["conditional_net_mean_bps"], 20 - 2 * 5.9 - .5)
        self.assertEqual(m["full_cost"]["required_gross_move_bps_to_break_even"], taker_cost)

    def test_maker_route_fee_diagnostic_and_expected_value(self):
        report = evaluate([row(i * 400, move=20, spread_bps=.5) for i in range(80)])
        maker = next(x for x in report["results"] if x["route"] == "MAKER")["metrics"]
        model = FillModel()
        maker_cost = simulate(0, "MAKER", model).total_cost_bps
        maker_diag_cost = model.maker_fee_bps + model.taker_fee_bps + .5
        conditional_net = 20 - maker_cost
        self.assertAlmostEqual(maker["observed_spread_fees_only"]["conditional_net_mean_bps"], 20 - maker_diag_cost)
        self.assertAlmostEqual(maker["observed_spread_fees_only"]["required_gross_move_mean_bps"], maker_diag_cost)
        self.assertAlmostEqual(maker["full_cost"]["conditional_net_mean_bps"], conditional_net)
        self.assertAlmostEqual(maker["full_cost"]["expected_net_per_signal_bps"], model.maker_fill_probability * conditional_net)
        self.assertEqual(maker["full_cost"]["required_gross_move_bps_to_break_even"], maker_cost)

    def test_non_overlap_uses_label_horizon(self):
        rows = [row(0, future_ts=10), row(5, future_ts=15), row(10, future_ts=20)]
        chosen, counts = select_non_overlapping(rows, "FLOW_PRICE_CONFIRM_LONG", 60,
                                                thresholds(rows), 1)
        self.assertEqual([x[0] for x in chosen], [0, 10])
        self.assertEqual(counts["skip_count"], 1)

    def test_chronological_split_and_boundary_purge(self):
        rows = [row(i, future_ts=future) for i, future in enumerate((1, 2, 3, 4, 5))]
        train, holdout, start = chronological_split(rows)
        self.assertEqual(len(train), 3)
        self.assertEqual(len(holdout), 2)
        self.assertEqual(start, 3)
        self.assertEqual([r["ts"] for r in purge_training_rows(train, start, 60)], [0, 1, 2])

    def test_thresholds_use_train_only_and_results_deterministic(self):
        rows = [row(i * 400, imb5=i / 100, delta5=i / 100, delta30=i / 100,
                    ret5=i / 1000, ret30=i / 1000) for i in range(100)]
        train, holdout, _ = chronological_split(rows)
        fitted = thresholds(train)
        for r in holdout:
            r.update(imb5=9999, delta5=9999, delta30=9999, ret5=9999, ret30=9999)
        a, b = evaluate(rows), evaluate(rows)
        self.assertEqual(a["split"]["thresholds"], fitted)
        self.assertEqual(a, b)

    def test_path_extrema_explicitly_unavailable(self):
        report = evaluate([row(i * 400) for i in range(100)])
        metric = report["results"][0]["metrics"]
        self.assertIsNone(metric["mfe_bps"])
        self.assertIsNone(metric["mae_bps"])


if __name__ == "__main__":
    unittest.main()
