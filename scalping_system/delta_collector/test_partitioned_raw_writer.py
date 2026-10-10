import gzip
import json
import tempfile
import unittest
from pathlib import Path

from delta_collector.partitioned_raw_writer import PartitionedGzipJSONLWriter


class PartitionedWriterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def read_rows(self, paths):
        rows = []
        for path in paths:
            with gzip.open(path, "rt", encoding="utf-8") as fh:
                rows.extend(json.loads(line) for line in fh if line.strip())
        return rows

    def test_compressed_jsonl_preserves_order_and_payload(self):
        original = [
            {"message": {"type": "trades", "sequence": 41, "p": "100.1"}, "receive_mono_ns": 10},
            {"message": {"type": "ob_l2", "sequence": 42, "b": [["100", "2"]]}, "receive_mono_ns": 20},
        ]
        writer = PartitionedGzipJSONLWriter(self.root, "unit_test", max_part_bytes=4096)
        paths = [writer.write(row) for row in original]
        writer.close()
        self.assertEqual(self.read_rows(sorted(set(paths))), original)
        self.assertEqual(paths[0], paths[1])
        self.assertTrue(paths[0].name.endswith("part_0001.jsonl.gz"))

    def test_rotates_without_losing_or_reindexing_records(self):
        writer = PartitionedGzipJSONLWriter(self.root, "rotate", max_part_bytes=100)
        for sequence in range(20):
            writer.write({"message": {"sequence": sequence, "payload": "x" * 25}})
        writer.close()
        paths = sorted(self.root.glob("session_rotate_part_*.jsonl.gz"))
        rows = self.read_rows(paths)
        self.assertGreater(len(paths), 1)
        self.assertEqual([row["message"]["sequence"] for row in rows], list(range(20)))

    def test_never_overwrites_existing_partition(self):
        existing = self.root / "session_fixed_part_0001.jsonl.gz"
        with gzip.open(existing, "wt", encoding="utf-8") as fh:
            fh.write(json.dumps({"sentinel": True}) + "\n")
        before = existing.read_bytes()
        writer = PartitionedGzipJSONLWriter(self.root, "fixed", max_part_bytes=4096)
        self.assertTrue(writer.current_path.name.endswith("part_0002.jsonl.gz"))
        writer.write({"new": True})
        writer.close()
        self.assertEqual(existing.read_bytes(), before)

    def test_close_is_idempotent_and_write_after_close_fails(self):
        writer = PartitionedGzipJSONLWriter(self.root, "close")
        writer.write({"ok": 1})
        writer.close()
        writer.close()
        with self.assertRaises(ValueError):
            writer.write({"bad": 2})

    def test_simulated_websocket_disconnect_finalizes_then_reconnects_cleanly(self):
        # A WebSocket disconnect is represented by the worker stopping and the
        # session writer being closed cleanly; the next process uses the same ID.
        first = PartitionedGzipJSONLWriter(self.root, "disconnect", max_part_bytes=4096)
        first.write({"event": 1, "receive_epoch_ns": 100})
        first_path = first.current_path
        first.close()
        with gzip.open(first_path, "rt", encoding="utf-8") as fh:
            self.assertEqual([json.loads(line) for line in fh], [{"event": 1, "receive_epoch_ns": 100}])

        second = PartitionedGzipJSONLWriter(self.root, "disconnect", max_part_bytes=4096)
        second.write({"event": 2, "receive_epoch_ns": 200})
        second_path = second.current_path
        second.close()
        self.assertNotEqual(first_path, second_path)
        self.assertEqual(self.read_rows([first_path, second_path]), [
            {"event": 1, "receive_epoch_ns": 100},
            {"event": 2, "receive_epoch_ns": 200},
        ])


if __name__ == "__main__":
    unittest.main()
