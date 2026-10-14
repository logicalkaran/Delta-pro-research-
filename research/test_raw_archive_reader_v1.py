import gzip
import json
from pathlib import Path

import pytest

from research.raw_archive_reader_v1 import iter_raw_records, stream_session_archive


def _part(path: Path, records):
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        for row in records:
            fh.write(json.dumps(row) + "\n")


def test_stream_session_archive_orders_numeric_partitions_and_streams_records(tmp_path):
    _part(tmp_path / "session_alpha_part_0002.jsonl.gz", [{"n": 2}, {"n": 3}])
    _part(tmp_path / "session_alpha_part_0001.jsonl.gz", [{"n": 1}])
    assert [x["n"] for x in stream_session_archive("alpha", tmp_path)] == [1, 2, 3]


def test_reader_rejects_implicit_merge_of_multiple_sessions(tmp_path):
    _part(tmp_path / "session_alpha_part_0001.jsonl.gz", [{"n": 1}])
    _part(tmp_path / "session_beta_part_0001.jsonl.gz", [{"n": 2}])
    with pytest.raises(ValueError, match="multiple gzip sessions"):
        list(iter_raw_records(data_dir=tmp_path, legacy_path=tmp_path / "missing.jsonl"))


def test_legacy_fallback_only_when_no_partitions(tmp_path):
    legacy = tmp_path / "legacy.jsonl"
    legacy.write_text('{"tail": true}\n', encoding="utf-8")
    assert list(iter_raw_records(data_dir=tmp_path / "empty", legacy_path=legacy)) == [{"tail": True}]
