"""Synthetic verification for BTC data hygiene and split invariants."""
import json
import tempfile
import unittest
from pathlib import Path

from research.data_hygiene import (
    classify_schema,
    deduplicate_records,
    normalize_and_sort,
    normalize_timestamp,
    purged_walk_forward_splits,
    timestamp_from_record,
)
from research.dataset_manifest import build_manifest
from research import quarantine_flagged_files as quarantine_mod


class TimestampTests(unittest.TestCase):
    def test_iso_timestamp(self):
        self.assertAlmostEqual(
            normalize_timestamp("2026-10-09T00:00:00Z"),
            1791504000.0,
            delta=1.0,
        )

    def test_explicit_units(self):
        seconds = 1791530412.0
        self.assertAlmostEqual(normalize_timestamp(seconds * 1e9, "timestamp_ns"), seconds)
        self.assertAlmostEqual(normalize_timestamp(seconds * 1e6, "timestamp_us"), seconds)
        self.assertAlmostEqual(normalize_timestamp(seconds * 1e3, "timestamp_ms"), seconds)

    def test_nested_delta_message_timestamp(self):
        ts, key = timestamp_from_record({"message": {"ts": 1791573264370522}})
        self.assertAlmostEqual(ts, 1791573264.370522, places=4)
        self.assertEqual(key, "message.ts")

    def test_missing_timestamp_rejected(self):
        with self.assertRaises(ValueError):
            timestamp_from_record({"event": "trade"})

    def test_non_finite_numeric_timestamps_rejected(self):
        for value in (float("nan"), float("inf"), float("-inf"), "nan", "inf"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    normalize_timestamp(value)

    def test_naive_iso_timestamp_is_interpreted_as_utc(self):
        self.assertEqual(
            normalize_timestamp("2026-10-09T00:00:00"),
            normalize_timestamp("2026-10-09T00:00:00Z"),
        )

    def test_sort_reports_inversions_and_preserves_rows(self):
        result = normalize_and_sort([
            {"ts": 3.0, "event_type": "trade", "sequence_id": 2},
            {"ts": 1.0, "event_type": "trade", "sequence_id": 1},
            {"ts": 2.0, "event_type": "trade", "sequence_id": 3},
            {"event": "missing timestamp"},
        ])
        self.assertEqual(result["input_records"], 4)
        self.assertEqual(result["timestamp_missing_or_invalid"], 1)
        self.assertEqual(result["original_order_inversions"], 1)
        self.assertEqual([r["ts_utc_s"] for r in result["records"]], [1.0, 2.0, 3.0])


class DeduplicationTests(unittest.TestCase):
    def test_preserves_long_short_pair_and_drops_exact_label_duplicate(self):
        rows = [
            {"ts": 1000.0, "direction": "LONG", "horizon_sec": 300, "label": 1},
            {"ts": 1000.0, "direction": "SHORT", "horizon_sec": 300, "label": 0},
            {"ts": 1000.0, "direction": "LONG", "horizon_sec": 300, "label": 1},
        ]
        result = deduplicate_records(rows)
        self.assertEqual(result["kept_records"], 2)
        self.assertEqual({r["direction"] for r in result["records"]}, {"LONG", "SHORT"})
        self.assertEqual(result["dropped_counts"]["duplicate"], 1)

    def test_distinct_ticks_at_same_timestamp_survive(self):
        rows = [
            {"ts": 1000.0, "type": "trade", "price": 10, "size": 1, "trade_id": "a"},
            {"ts": 1000.0, "type": "trade", "price": 10, "size": 2, "trade_id": "b"},
            {"ts": 1000.0, "type": "trade", "price": 10, "size": 1, "trade_id": "a"},
        ]
        result = deduplicate_records(rows)
        self.assertEqual(result["kept_records"], 2)

    def test_schema_categories(self):
        self.assertEqual(classify_schema({"labels": {"60": {"move_bps": 2}}}), "labeled_dataset")
        self.assertEqual(classify_schema({"imb5": 0.1, "delta5": 2}), "derived_features")
        self.assertEqual(classify_schema({"order_id": "o1"}), "execution_journal")
        self.assertEqual(classify_schema({"price": 10, "size": 1, "trade_id": "t"}), "market_trades")


class ManifestTests(unittest.TestCase):
    def test_manifest_flags_identical_files_missing_time_and_inversion(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            data = root / "data"
            data.mkdir()
            (data / "a.jsonl").write_text(
                '{"ts":3,"price":10,"size":1,"trade_id":"a"}\n'
                '{"ts":2,"price":11,"size":1,"trade_id":"b"}\n',
                encoding="utf-8",
            )
            (data / "b.jsonl").write_bytes((data / "a.jsonl").read_bytes())
            (data / "missing.jsonl").write_text('{"event":"unknown"}\n', encoding="utf-8")
            manifest = build_manifest(data, root)
            self.assertEqual(manifest["source_files"], 3)
            self.assertEqual(len(manifest["duplicate_file_groups"]), 1)
            by_path = {r["relative_path"]: r for r in manifest["files"]}
            self.assertEqual(by_path["data/a.jsonl"]["out_of_order_timestamps"], 1)
            self.assertEqual(by_path["data/missing.jsonl"]["missing_timestamps"], 1)
            self.assertTrue(all(by_path[p]["integrity_status"] == "REVISE" for p in ("data/a.jsonl", "data/b.jsonl", "data/missing.jsonl")))
            self.assertFalse(manifest["quarantine_policy"]["automatic_moves"])


class QuarantineTests(unittest.TestCase):
    def test_dry_run_preserves_source_and_apply_hash_verifies_move(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            data = root / "data"
            data.mkdir()
            source = data / "bad.jsonl"
            source.write_text('{"event":"missing timestamp"}\n', encoding="utf-8")
            manifest = build_manifest(data, root)
            manifest_path = data / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            old_root = quarantine_mod.ROOT
            quarantine_mod.ROOT = root
            try:
                dry = quarantine_mod.quarantine(manifest_path, root / "quarantine", apply=False)
                self.assertEqual(dry["moved_count"], 0)
                self.assertTrue(source.exists())
                applied = quarantine_mod.quarantine(manifest_path, root / "quarantine", apply=True)
                self.assertEqual(applied["moved_count"], 1)
                self.assertFalse(source.exists())
                self.assertTrue((root / "quarantine" / "bad.jsonl").exists())
            finally:
                quarantine_mod.ROOT = old_root


class PurgedSplitTests(unittest.TestCase):
    def test_horizon_purge_and_embargo(self):
        rows = [{"ts_utc_s": float(i), "future_ts": float(i + 300)} for i in range(2000)]
        result = purged_walk_forward_splits(rows, splits=3, max_horizon_sec=300, embargo_sec=60)
        self.assertEqual(len(result["folds"]), 3)
        self.assertTrue(all(f["status"] == "PASS" for f in result["folds"]))
        for fold in result["folds"]:
            if fold["train_max_ts"] is not None:
                self.assertLessEqual(fold["train_max_ts"], fold["test_start_ts"] - 300)
            self.assertFalse(fold["boundary_leakage"])
            self.assertEqual(fold["direct_label_boundary_leakage"], 0)

    def test_invalid_parameters_fail_closed(self):
        with self.assertRaises(ValueError):
            purged_walk_forward_splits([], splits=0)
        self.assertEqual(
            purged_walk_forward_splits([{"ts_utc_s": 1.0}], splits=2)["status"],
            "REVISE",
        )

    def test_overlapping_label_horizon_is_removed_from_training(self):
        rows = [
            {"ts_utc_s": float(i), "label_end_ts": float(i + 20)}
            for i in range(120)
        ]
        result = purged_walk_forward_splits(
            rows, splits=2, max_horizon_sec=5, embargo_sec=0
        )
        self.assertEqual(len(result["folds"]), 2)
        for fold in result["folds"]:
            boundary = fold["test_start_ts"]
            train = [r for r in rows if r["ts_utc_s"] <= fold["train_max_ts"]] if fold["train_max_ts"] is not None else []
            self.assertTrue(all(r["label_end_ts"] <= boundary for r in train))

    def test_malformed_future_timestamp_fails_closed_for_training_row(self):
        rows = [{"ts_utc_s": float(i)} for i in range(80)]
        # Place a malformed realization timestamp on an otherwise eligible row.
        rows[0]["future_ts"] = "not-a-timestamp"
        result = purged_walk_forward_splits(
            rows, splits=2, max_horizon_sec=1, embargo_sec=0
        )
        self.assertEqual(len(result["folds"]), 2)
        self.assertTrue(any(fold["direct_label_boundary_leakage"] >= 1 for fold in result["folds"]))
        # The malformed row is excluded from training rather than trusted.
        for fold in result["folds"]:
            self.assertNotIn(0, fold["train_indices"])

    def test_duplicate_timestamps_remain_chronologically_deterministic(self):
        rows = [{"ts_utc_s": float(i // 2)} for i in range(160)]
        result = purged_walk_forward_splits(
            rows, splits=3, max_horizon_sec=2, embargo_sec=0
        )
        self.assertEqual(len(result["folds"]), 3)
        for fold in result["folds"]:
            if fold["train_max_ts"] is not None:
                self.assertLessEqual(fold["train_max_ts"], fold["test_start_ts"] - 2)
            self.assertFalse(fold["boundary_leakage"])


if __name__ == "__main__":
    unittest.main()
