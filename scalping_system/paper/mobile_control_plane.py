"""Paper-only mobile control plane primitives. No broker or order-submission capability."""
from __future__ import annotations

import hashlib
import hmac
import json
from contextlib import closing
import math
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any

SCHEMA = 1


def _finite_positive(value: Any, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(result) or result <= 0:
        raise ValueError(f"{name} must be finite and > 0")
    return result


def size_linear_position(
    *, equity: float, risk_fraction: float, entry: float, stop: float,
    target: float, side: str, lot_size: float = 1.0,
    value_per_price_unit: float = 1.0, estimated_cost_per_unit: float = 0.0,
    max_notional_fraction: float = 1.0,
) -> dict:
    """Conservative linear-instrument sizing; contract-specific multipliers must be verified."""
    equity = _finite_positive(equity, "equity")
    entry = _finite_positive(entry, "entry")
    stop = _finite_positive(stop, "stop")
    target = _finite_positive(target, "target")
    lot_size = _finite_positive(lot_size, "lot_size")
    multiplier = _finite_positive(value_per_price_unit, "value_per_price_unit")
    risk_fraction = float(risk_fraction)
    max_notional_fraction = float(max_notional_fraction)
    cost = float(estimated_cost_per_unit)
    if not math.isfinite(risk_fraction) or not 0 < risk_fraction <= 0.01:
        raise ValueError("risk_fraction must be > 0 and <= 1% (hard research ceiling)")
    if not math.isfinite(max_notional_fraction) or not 0 < max_notional_fraction <= 1:
        raise ValueError("max_notional_fraction must be in (0, 1]")
    if not math.isfinite(cost) or cost < 0:
        raise ValueError("estimated_cost_per_unit must be finite and >= 0")
    side = str(side).upper()
    if side not in ("LONG", "SHORT"):
        raise ValueError("side must be LONG or SHORT")
    if side == "LONG" and not (stop < entry < target):
        raise ValueError("LONG requires stop < entry < target")
    if side == "SHORT" and not (target < entry < stop):
        raise ValueError("SHORT requires target < entry < stop")

    price_risk = abs(entry - stop) * multiplier
    unit_risk = price_risk + cost
    risk_budget = equity * risk_fraction
    raw_qty = risk_budget / unit_risk
    qty = math.floor((raw_qty + 1e-12) / lot_size) * lot_size
    notional_cap = equity * max_notional_fraction
    qty = min(qty, math.floor((notional_cap / (entry * multiplier) + 1e-12) / lot_size) * lot_size)
    estimated_risk = qty * unit_risk
    reward_per_unit = abs(target - entry) * multiplier - cost
    reward = qty * max(0.0, reward_per_unit)
    ratio = reward / estimated_risk if estimated_risk > 0 else 0.0
    return {
        "equity": equity, "risk_fraction": risk_fraction,
        "risk_budget": risk_budget, "entry": entry, "stop": stop,
        "target": target, "side": side, "quantity": qty,
        "lot_size": lot_size, "unit_risk_including_cost": unit_risk,
        "estimated_risk": estimated_risk, "estimated_reward_net_cost": reward,
        "reward_risk_ratio_net_cost": ratio,
        "notional_estimate": qty * entry * multiplier,
        "size_valid": qty >= lot_size and estimated_risk <= risk_budget + 1e-8,
        "paper_only": True, "real_orders": False,
    }


def make_proposal(*, instrument: str, sizing: dict, source: str,
                  created_at: float | None = None, ttl_seconds: int = 60) -> dict:
    if sizing.get("paper_only") is not True or sizing.get("real_orders") is not False:
        raise ValueError("proposal sizing must explicitly be paper-only")
    if not sizing.get("size_valid"):
        raise ValueError("position size is zero or violates risk budget")
    if not instrument or not source:
        raise ValueError("instrument and source are required")
    if not isinstance(ttl_seconds, int) or not 1 <= ttl_seconds <= 300:
        raise ValueError("ttl_seconds must be 1..300")
    now = time.time() if created_at is None else _finite_positive(created_at, "created_at")
    proposal = {
        "schema": SCHEMA, "proposal_id": secrets.token_hex(16),
        "instrument": str(instrument), "source": str(source),
        "created_at": now, "expires_at": now + ttl_seconds,
        "sizing": sizing, "status": "PENDING",
        "paper_only": True, "real_orders": False,
    }
    canonical = json.dumps(proposal, sort_keys=True, separators=(",", ":"), allow_nan=False)
    proposal["proposal_hash"] = hashlib.sha256(canonical.encode()).hexdigest()
    return proposal


def sign_approval(proposal: dict, secret: bytes, *, action: str = "APPROVE") -> dict:
    """Create a signed callback payload; caller must keep secret outside source control."""
    if not secret or len(secret) < 32:
        raise ValueError("approval secret must be at least 32 bytes")
    action = str(action).upper()
    if action not in ("APPROVE", "DISMISS", "KILL"):
        raise ValueError("unsupported action")
    body = {
        "proposal_id": proposal.get("proposal_id"),
        "proposal_hash": proposal.get("proposal_hash"),
        "expires_at": proposal.get("expires_at"),
        "action": action,
        "nonce": secrets.token_hex(16),
    }
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False)
    body["signature"] = hmac.new(secret, encoded.encode(), hashlib.sha256).hexdigest()
    return body


class ApprovalLedger:
    """SQLite-backed one-use callback ledger. It records decisions only; it cannot place orders."""
    def __init__(self, path: str | Path, secret: bytes):
        if not secret or len(secret) < 32:
            raise ValueError("approval secret must be at least 32 bytes")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.secret = secret
        with closing(self._connect()) as db:
            with db:
                db.execute("""CREATE TABLE IF NOT EXISTS callbacks (
                nonce TEXT PRIMARY KEY, proposal_id TEXT NOT NULL,
                proposal_hash TEXT NOT NULL, action TEXT NOT NULL,
                expires_at REAL NOT NULL, consumed_at REAL NOT NULL)""")
                db.execute("""CREATE TABLE IF NOT EXISTS control_state (
                key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at REAL NOT NULL)""")

    def _connect(self):
        db = sqlite3.connect(str(self.path), timeout=10, isolation_level="IMMEDIATE")
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        return db

    def is_killed(self) -> bool:
        with closing(self._connect()) as db:
            row = db.execute("SELECT value FROM control_state WHERE key=?", ("kill_active",)).fetchone()
        return bool(row and row[0] == "true")

    def consume(self, proposal: dict, callback: dict, *, now: float | None = None) -> dict:
        current = time.time() if now is None else float(now)
        supplied_sig = callback.get("signature", "")
        body = {k: callback.get(k) for k in
                ("proposal_id", "proposal_hash", "expires_at", "action", "nonce")}
        encoded = json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False)
        expected = hmac.new(self.secret, encoded.encode(), hashlib.sha256).hexdigest()
        if not isinstance(supplied_sig, str) or not hmac.compare_digest(supplied_sig, expected):
            raise ValueError("invalid callback signature")
        if body["proposal_id"] != proposal.get("proposal_id"):
            raise ValueError("proposal ID mismatch")
        proposal_payload = dict(proposal)
        supplied_proposal_hash = proposal_payload.pop("proposal_hash", None)
        canonical_proposal = json.dumps(proposal_payload, sort_keys=True,
                                        separators=(",", ":"), allow_nan=False)
        actual_proposal_hash = hashlib.sha256(canonical_proposal.encode()).hexdigest()
        if (body["proposal_hash"] != supplied_proposal_hash
                or not hmac.compare_digest(str(supplied_proposal_hash), actual_proposal_hash)):
            raise ValueError("proposal hash mismatch or proposal tampering")
        if body["expires_at"] != proposal.get("expires_at") or current > float(body["expires_at"]):
            raise ValueError("proposal expired or expiry mismatch")
        if body["action"] not in ("APPROVE", "DISMISS", "KILL"):
            raise ValueError("invalid callback action")
        if proposal.get("paper_only") is not True or proposal.get("real_orders") is not False:
            raise ValueError("unsafe proposal authority flags")
        if body["action"] == "APPROVE" and self.is_killed():
            raise ValueError("kill lock active; approvals disabled")
        with closing(self._connect()) as db:
            try:
                with db:
                    db.execute("INSERT INTO callbacks VALUES (?, ?, ?, ?, ?, ?)", (
                    body["nonce"], body["proposal_id"], body["proposal_hash"],
                    body["action"], float(body["expires_at"]), current))
                    if body["action"] == "KILL":
                        db.execute("INSERT INTO control_state VALUES (?, ?, ?) "
                                   "ON CONFLICT(key) DO UPDATE SET value=excluded.value, "
                                   "updated_at=excluded.updated_at",
                                   ("kill_active", "true", current))
            except sqlite3.IntegrityError as exc:
                raise ValueError("callback nonce already consumed") from exc
        return {
            "decision": body["action"], "proposal_id": body["proposal_id"],
            "consumed_at": current, "paper_only": True, "real_orders": False,
            "broker_action_taken": False,
        }


class SignalStateStore:
    """Persistent idempotent proposal lifecycle; terminal decisions never invoke a broker."""
    TRANSITIONS = {
        "QUEUED": {"APPROVED", "DISMISSED", "EXPIRED", "KILLED"},
        "APPROVED": {"EXPIRED", "KILLED"},
        "DISMISSED": set(), "EXPIRED": set(), "KILLED": set(),
    }

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as db:
            with db:
                db.execute("""CREATE TABLE IF NOT EXISTS signals (
                    proposal_id TEXT PRIMARY KEY, proposal_hash TEXT NOT NULL,
                    instrument TEXT NOT NULL, state TEXT NOT NULL,
                    created_at REAL NOT NULL, expires_at REAL NOT NULL,
                    updated_at REAL NOT NULL, decision_nonce TEXT UNIQUE)""")
                db.execute("""CREATE TABLE IF NOT EXISTS signal_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    proposal_id TEXT NOT NULL, from_state TEXT, to_state TEXT NOT NULL,
                    at REAL NOT NULL, reason TEXT NOT NULL)""")
                db.execute("""CREATE TABLE IF NOT EXISTS control_state (
                    key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at REAL NOT NULL)""")

    def _connect(self):
        db = sqlite3.connect(str(self.path), timeout=10, isolation_level="IMMEDIATE")
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        return db

    def is_killed(self) -> bool:
        with closing(self._connect()) as db:
            row = db.execute("SELECT value FROM control_state WHERE key=?", ("kill_active",)).fetchone()
        return bool(row and row[0] == "true")

    def activate_kill(self, *, now: float | None = None, reason: str = "OPERATOR_KILL") -> None:
        current = time.time() if now is None else float(now)
        with closing(self._connect()) as db:
            with db:
                db.execute("INSERT INTO control_state VALUES (?, ?, ?) "
                           "ON CONFLICT(key) DO UPDATE SET value=excluded.value, "
                           "updated_at=excluded.updated_at", ("kill_active", "true", current))
                active = db.execute("SELECT proposal_id, state FROM signals "
                                    "WHERE state IN ('QUEUED','APPROVED')").fetchall()
                for proposal_id, old_state in active:
                    db.execute("UPDATE signals SET state='KILLED', updated_at=? WHERE proposal_id=?",
                               (current, proposal_id))
                    db.execute("INSERT INTO signal_events(proposal_id,from_state,to_state,at,reason) "
                               "VALUES (?,?,?,?,?)",
                               (proposal_id, old_state, "KILLED", current, reason))

    def queue(self, proposal: dict, *, now: float | None = None) -> dict:
        current = time.time() if now is None else float(now)
        proposal_id = proposal.get("proposal_id")
        if not proposal_id or not proposal.get("proposal_hash"):
            raise ValueError("proposal ID/hash required")
        if proposal.get("paper_only") is not True or proposal.get("real_orders") is not False:
            raise ValueError("unsafe proposal authority flags")
        if float(proposal.get("expires_at", 0)) <= current:
            raise ValueError("cannot queue an expired proposal")
        with closing(self._connect()) as db:
            with db:
                row = db.execute("SELECT proposal_hash, state FROM signals WHERE proposal_id=?",
                                 (proposal_id,)).fetchone()
                if row:
                    if row[0] != proposal["proposal_hash"]:
                        raise ValueError("proposal ID collision with different hash")
                    return {"proposal_id": proposal_id, "state": row[1], "idempotent": True}
                db.execute("INSERT INTO signals VALUES (?, ?, ?, ?, ?, ?, ?, NULL)", (
                    proposal_id, proposal["proposal_hash"], proposal["instrument"], "QUEUED",
                    float(proposal["created_at"]), float(proposal["expires_at"]), current))
                db.execute("INSERT INTO signal_events(proposal_id,from_state,to_state,at,reason) "
                           "VALUES (?,NULL,'QUEUED',?,'PROPOSAL_CREATED')", (proposal_id, current))
        return {"proposal_id": proposal_id, "state": "QUEUED", "idempotent": False}

    def transition(self, proposal_id: str, to_state: str, *, now: float | None = None,
                   reason: str = "OPERATOR_DECISION", nonce: str | None = None) -> dict:
        current = time.time() if now is None else float(now)
        to_state = str(to_state).upper()
        if to_state not in {"APPROVED", "DISMISSED", "EXPIRED", "KILLED"}:
            raise ValueError("invalid target state")
        with closing(self._connect()) as db:
            with db:
                row = db.execute("SELECT state, expires_at, decision_nonce FROM signals "
                                 "WHERE proposal_id=?", (proposal_id,)).fetchone()
                if not row:
                    raise ValueError("unknown proposal")
                old, expires_at, used_nonce = row
                if old == to_state:
                    return {"proposal_id": proposal_id, "state": old, "idempotent": True}
                if to_state not in self.TRANSITIONS.get(old, set()):
                    raise ValueError(f"invalid transition {old}->{to_state}")
                if to_state == "APPROVED" and current > expires_at:
                    raise ValueError("expired proposal cannot be approved")
                if to_state == "APPROVED":
                    kill = db.execute("SELECT value FROM control_state WHERE key=?",
                                      ("kill_active",)).fetchone()
                    if kill and kill[0] == "true":
                        raise ValueError("kill lock active; approval disabled")
                if nonce and used_nonce == nonce:
                    raise ValueError("decision nonce already used")
                db.execute("UPDATE signals SET state=?, updated_at=?, decision_nonce=? "
                           "WHERE proposal_id=? AND state=?",
                           (to_state, current, nonce, proposal_id, old))
                db.execute("INSERT INTO signal_events(proposal_id,from_state,to_state,at,reason) "
                           "VALUES (?,?,?,?,?)", (proposal_id, old, to_state, current, reason))
        return {"proposal_id": proposal_id, "state": to_state, "idempotent": False,
                "broker_action_taken": False, "real_orders": False}

    def expire_due(self, *, now: float | None = None) -> list[str]:
        current = time.time() if now is None else float(now)
        with closing(self._connect()) as db:
            rows = db.execute("SELECT proposal_id FROM signals WHERE state='QUEUED' "
                              "AND expires_at < ?", (current,)).fetchall()
        expired = []
        for (proposal_id,) in rows:
            self.transition(proposal_id, "EXPIRED", now=current, reason="TTL_EXPIRED")
            expired.append(proposal_id)
        return expired

    def get(self, proposal_id: str) -> dict | None:
        with closing(self._connect()) as db:
            row = db.execute("SELECT proposal_id, instrument, state, created_at, expires_at, "
                             "updated_at FROM signals WHERE proposal_id=?", (proposal_id,)).fetchone()
        if not row:
            return None
        return dict(zip(("proposal_id", "instrument", "state", "created_at", "expires_at",
                         "updated_at"), row))

    def status(self) -> dict:
        with closing(self._connect()) as db:
            rows = db.execute("SELECT state, COUNT(*) FROM signals GROUP BY state").fetchall()
        return {"states": {state: count for state, count in rows},
                "paper_only": True, "real_orders": False}


def process_mobile_callback(proposal: dict, callback: dict, *,
                            ledger: ApprovalLedger, store: SignalStateStore,
                            now: float | None = None) -> dict:
    """Apply a verified mobile decision to the persistent shadow state machine."""
    if ledger.path.resolve() != store.path.resolve():
        raise ValueError("approval ledger and signal state must share one SQLite database")
    current = time.time() if now is None else float(now)
    if store.get(proposal.get("proposal_id")) is None:
        raise ValueError("proposal must be queued before callback handling")
    decision = ledger.consume(proposal, callback, now=current)
    if decision["decision"] == "KILL":
        store.activate_kill(now=current, reason="SIGNED_MOBILE_KILL")
        return {**decision, "kill_lock_active": True, "broker_action_taken": False}
    target = {"APPROVE": "APPROVED", "DISMISS": "DISMISSED"}[decision["decision"]]
    state = store.transition(proposal["proposal_id"], target, now=current,
                             reason="SIGNED_MOBILE_" + decision["decision"],
                             nonce=callback["nonce"])
    return {**decision, "state": state["state"], "kill_lock_active": store.is_killed(),
            "broker_action_taken": False, "real_orders": False}
