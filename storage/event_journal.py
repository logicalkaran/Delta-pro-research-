"""Append-only, hash-chained SQLite event journal for the edge trading node.

This is an execution-state journal, not an exchange adapter. It never submits,
cancels or modifies orders. SQLite WAL is enabled; events are append-only and
the hash chain detects edits, deletions and reordering inside the retained chain.
Tail truncation is detectable only when verify() receives an independently
retained expected terminal hash and sequence from outside this database.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Any

GENESIS = "0" * 64


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


class EventJournal:
    def __init__(self, path: str | Path, *, synchronous: str = "FULL") -> None:
        if synchronous not in {"FULL", "NORMAL"}:
            raise ValueError("synchronous must be FULL or NORMAL")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.path), timeout=5.0)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute(f"PRAGMA synchronous={synchronous}")
        self.db.execute("PRAGMA busy_timeout=5000")
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS events (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                ts_ns INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                previous_hash TEXT NOT NULL,
                event_hash TEXT NOT NULL UNIQUE
            )
        """)
        self.db.commit()

    @staticmethod
    def _digest(seq: int, event_id: str, ts_ns: int, event_type: str,
                payload_json: str, previous_hash: str) -> str:
        material = canonical_json({
            "seq": seq, "event_id": event_id, "ts_ns": ts_ns,
            "event_type": event_type, "payload_json": payload_json,
            "previous_hash": previous_hash,
        })
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    def append(self, event_id: str, event_type: str, payload: dict[str, Any],
               *, ts_ns: int | None = None) -> dict[str, Any]:
        if not event_id or not event_type:
            raise ValueError("event_id and event_type are required")
        payload_json = canonical_json(payload)
        stamp = time.time_ns() if ts_ns is None else int(ts_ns)
        try:
            with self.db:
                last = self.db.execute(
                    "SELECT seq, event_hash FROM events ORDER BY seq DESC LIMIT 1"
                ).fetchone()
                previous_hash = last["event_hash"] if last else GENESIS
                seq = (last["seq"] + 1) if last else 1
                digest = self._digest(seq, event_id, stamp, event_type, payload_json, previous_hash)
                self.db.execute(
                    "INSERT INTO events(event_id,ts_ns,event_type,payload_json,previous_hash,event_hash) "
                    "VALUES(?,?,?,?,?,?)",
                    (event_id, stamp, event_type, payload_json, previous_hash, digest),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError("duplicate event_id or hash; event was not appended") from exc
        return {
            "seq": seq, "event_id": event_id, "ts_ns": stamp, "event_type": event_type,
            "payload": payload, "previous_hash": previous_hash, "event_hash": digest,
        }

    def verify(self, *, expected_terminal_hash: str | None = None,
               expected_last_seq: int | None = None) -> dict[str, Any]:
        rows = self.db.execute("SELECT * FROM events ORDER BY seq").fetchall()
        previous = GENESIS
        expected_seq = 1
        for row in rows:
            if row["seq"] != expected_seq:
                return {"valid": False, "reason": "SEQUENCE_GAP", "at_seq": row["seq"]}
            if row["previous_hash"] != previous:
                return {"valid": False, "reason": "PREVIOUS_HASH_MISMATCH", "at_seq": row["seq"]}
            digest = self._digest(
                row["seq"], row["event_id"], row["ts_ns"], row["event_type"],
                row["payload_json"], row["previous_hash"],
            )
            if digest != row["event_hash"]:
                return {"valid": False, "reason": "EVENT_HASH_MISMATCH", "at_seq": row["seq"]}
            previous = digest
            expected_seq += 1
        last_seq = expected_seq - 1
        if expected_terminal_hash is not None and previous != expected_terminal_hash:
            return {"valid": False, "reason": "TERMINAL_HASH_ANCHOR_MISMATCH", "last_seq": last_seq}
        if expected_last_seq is not None and last_seq != expected_last_seq:
            return {"valid": False, "reason": "TERMINAL_SEQUENCE_ANCHOR_MISMATCH", "last_seq": last_seq}
        return {
            "valid": True, "events": len(rows),
            "terminal_hash": previous, "last_seq": last_seq,
        }

    def replay(self, *, after_seq: int = 0) -> list[dict[str, Any]]:
        if after_seq < 0:
            raise ValueError("after_seq cannot be negative")
        integrity = self.verify()
        if not integrity["valid"]:
            raise RuntimeError("event journal integrity failure: " + integrity["reason"])
        rows = self.db.execute(
            "SELECT * FROM events WHERE seq > ? ORDER BY seq", (after_seq,)
        ).fetchall()
        return [{
            "seq": r["seq"], "event_id": r["event_id"], "ts_ns": r["ts_ns"],
            "event_type": r["event_type"], "payload": json.loads(r["payload_json"]),
            "previous_hash": r["previous_hash"], "event_hash": r["event_hash"],
        } for r in rows]

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> "EventJournal":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
