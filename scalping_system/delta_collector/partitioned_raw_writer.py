"""Immutable gzip-partitioned raw JSONL writer for research telemetry only.

Each partition is created exclusively and never overwritten. Records are preserved in
arrival order; payloads/sequence IDs are not rewritten or re-indexed. No trading APIs.
"""
from __future__ import annotations

import gzip
import io
import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _safe_session_id(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._-")
    return cleaned[:80] or uuid.uuid4().hex[:8]


class PartitionedGzipJSONLWriter:
    """Append JSON objects to exclusive, session-tagged gzip JSONL partitions.

    max_part_bytes measures uncompressed UTF-8 payload bytes. A record is never
    split across files. Each newline is flushed through gzip and the underlying file
    so abrupt socket drops lose at most the currently-writing record.
    """

    def __init__(
        self,
        directory: str | Path,
        session_id: str | None = None,
        max_part_bytes: int = 16 * 1024 * 1024,
        compresslevel: int = 4,
    ) -> None:
        if max_part_bytes < 1:
            raise ValueError("max_part_bytes must be >= 1")
        if not 1 <= compresslevel <= 9:
            raise ValueError("compresslevel must be between 1 and 9")
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        generated = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
        self.session_id = _safe_session_id(session_id or os.environ.get("SESSION_ID") or generated)
        self.max_part_bytes = int(max_part_bytes)
        self.compresslevel = int(compresslevel)
        self.part_index = 0
        self.part_uncompressed_bytes = 0
        self.records_written = 0
        self._raw = None
        self._gzip = None
        self._text = None
        self._closed = False
        self._open_next_part()

    @property
    def current_path(self) -> Path | None:
        if self.part_index < 1:
            return None
        return self.directory / f"session_{self.session_id}_part_{self.part_index:04d}.jsonl.gz"

    def _open_next_part(self) -> None:
        if self._closed:
            raise ValueError("writer is closed")
        while True:
            self.part_index += 1
            path = self.directory / f"session_{self.session_id}_part_{self.part_index:04d}.jsonl.gz"
            try:
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                break
            except FileExistsError:
                continue
        self._raw = os.fdopen(fd, "wb")
        try:
            self._gzip = gzip.GzipFile(fileobj=self._raw, mode="wb", compresslevel=self.compresslevel)
            self._text = io.TextIOWrapper(self._gzip, encoding="utf-8", newline="")
            self.part_uncompressed_bytes = 0
        except Exception:
            self._raw.close()
            path.unlink(missing_ok=True)
            raise

    def _close_part(self) -> None:
        text, gz, raw = self._text, self._gzip, self._raw
        self._text = self._gzip = self._raw = None
        if text is not None:
            text.flush()
            # TextIOWrapper closes GzipFile, which writes the gzip trailer.
            text.close()
        elif gz is not None:
            gz.close()
        if raw is not None and not raw.closed:
            raw.flush()
            os.fsync(raw.fileno())
            raw.close()

    def write(self, record: dict[str, Any]) -> Path:
        if self._closed:
            raise ValueError("writer is closed")
        line = json.dumps(record, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n"
        encoded_size = len(line.encode("utf-8"))
        if self.part_uncompressed_bytes and self.part_uncompressed_bytes + encoded_size > self.max_part_bytes:
            self._close_part()
            self._open_next_part()
        assert self._text is not None and self._raw is not None
        path = self.current_path
        self._text.write(line)
        self._text.flush()  # newline durability barrier; intentionally favors recovery over max throughput
        self._raw.flush()
        self.part_uncompressed_bytes += encoded_size
        self.records_written += 1
        assert path is not None
        return path

    def flush(self) -> None:
        if self._closed:
            return
        if self._text is not None:
            self._text.flush()
        if self._raw is not None:
            self._raw.flush()
            os.fsync(self._raw.fileno())

    def close(self) -> None:
        if self._closed:
            return
        try:
            self._close_part()
        finally:
            self._closed = True

    def __enter__(self) -> "PartitionedGzipJSONLWriter":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
