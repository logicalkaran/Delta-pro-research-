"""Streaming reader for immutable Delta gzip-session archives (research only).

Partition order is authoritative within one session. This deliberately refuses to
merge multiple sessions into a supposedly chronological stream without a merge step.
Legacy JSONL is used only when no gzip partitions exist, and is labeled as a tail.
"""
from __future__ import annotations

import gzip
import json
import re
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARCHIVE_DIR = ROOT / "data" / "raw" / "gzip_sessions"
DEFAULT_LEGACY_PATH = ROOT / "data" / "raw" / "delta_btc_raw.jsonl"
_PART_RE = re.compile(r"^session_(?P<session>.+)_part_(?P<part>\d+)\.jsonl\.gz$")


def _partition_key(path: Path) -> tuple[int, str]:
    match = _PART_RE.match(path.name)
    if not match:
        raise ValueError(f"not a session partition filename: {path.name}")
    return int(match.group("part")), path.name


def list_session_partitions(session_id: str, data_dir: str | Path = DEFAULT_ARCHIVE_DIR) -> list[Path]:
    if not session_id or not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", session_id) or ".." in session_id:
        raise ValueError("session_id must be a non-empty filename-safe session identifier")
    directory = Path(data_dir)
    found = []
    for path in directory.glob(f"session_{session_id}_part_*.jsonl.gz"):
        match = _PART_RE.match(path.name)
        if match and match.group("session") == session_id and path.is_file():
            found.append(path)
    return sorted(found, key=_partition_key)


def stream_session_archive(session_id: str, data_dir: str | Path = DEFAULT_ARCHIVE_DIR) -> Iterator[dict[str, Any]]:
    """Yield parsed records in arrival order, keeping memory bounded to one line."""
    files = list_session_partitions(session_id, data_dir)
    if not files:
        raise FileNotFoundError(f"no gzip partitions for session {session_id!r} in {data_dir}")
    for path in files:
        with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
            for line_no, line in enumerate(fh, 1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"invalid JSON at {path.name}:{line_no}: {exc}") from exc
                if not isinstance(record, dict):
                    raise ValueError(f"expected JSON object at {path.name}:{line_no}")
                yield record


def iter_raw_records(
    session_id: str | None = None,
    data_dir: str | Path = DEFAULT_ARCHIVE_DIR,
    legacy_path: str | Path = DEFAULT_LEGACY_PATH,
) -> Iterator[dict[str, Any]]:
    """Read one explicit session; use the legacy bounded mirror only if no archive exists.

    With no session_id, a single discovered session is accepted. Multiple sessions are
    rejected rather than falsely interleaved; callers must replay them separately.
    """
    directory = Path(data_dir)
    all_files = sorted(directory.glob("session_*_part_*.jsonl.gz")) if directory.exists() else []
    sessions = sorted({m.group("session") for p in all_files if (m := _PART_RE.match(p.name))})
    if session_id is not None:
        yield from stream_session_archive(session_id, directory)
        return
    if len(sessions) > 1:
        raise ValueError("multiple gzip sessions found; pass session_id and replay sessions separately")
    if len(sessions) == 1:
        yield from stream_session_archive(sessions[0], directory)
        return
    legacy = Path(legacy_path)
    if not legacy.is_file():
        raise FileNotFoundError(f"no gzip session archives and no legacy raw file at {legacy}")
    with legacy.open("rt", encoding="utf-8", newline="") as fh:
        for line_no, line in enumerate(fh, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON at {legacy}:{line_no}: {exc}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"expected JSON object at {legacy}:{line_no}")
            yield record
