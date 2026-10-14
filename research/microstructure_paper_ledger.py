"""Research-only SQLite WAL ledger with fail-closed mock risk evaluation."""
from __future__ import annotations
import json, math, sqlite3, time
from pathlib import Path
from risk.orchestration_oracle import PortfolioSnapshot, OrderIntent, RiskLimits, evaluate

SCHEMA = """
CREATE TABLE IF NOT EXISTS paper_events(
 event_id INTEGER PRIMARY KEY AUTOINCREMENT, event_ts REAL NOT NULL,
 kind TEXT NOT NULL, payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS simulated_parents(
 parent_id TEXT PRIMARY KEY, side TEXT NOT NULL, quantity_btc REAL NOT NULL,
 created_ts REAL NOT NULL, state TEXT NOT NULL, risk_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS simulated_children(
 child_id TEXT PRIMARY KEY, parent_id TEXT NOT NULL, ordinal INTEGER NOT NULL,
 quantity_btc REAL NOT NULL, state TEXT NOT NULL, fill_price REAL,
 fill_ts REAL, FOREIGN KEY(parent_id) REFERENCES simulated_parents(parent_id)
);
"""

class PaperLedger:
    """Only writes local paper records. Contains no exchange/network dependencies."""
    def __init__(self, path: str | Path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, timeout=5.0)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("PRAGMA busy_timeout=5000")
        self.db.executescript(SCHEMA)
        self.db.commit()

    def evaluate_intent(self, *, signed_quantity_btc: float, snapshot: dict | None,
                        limits: RiskLimits = RiskLimits()) -> dict:
        # No inferred account equity, anchors, positions, or margin defaults.
        if snapshot is None:
            return {"verdict":"REJECTED","approved_signed_quantity_btc":0.0,
                    "reason_codes":["MISSING_AUTHORITATIVE_ACCOUNT_STATE"],"live_orders_enabled":False}
        required={"mark_price","account_equity","current_position_btc","maintenance_margin_rate",
                  "day_start_equity","week_start_equity","peak_equity"}
        if not required.issubset(snapshot):
            return {"verdict":"REJECTED","approved_signed_quantity_btc":0.0,
                    "reason_codes":["INCOMPLETE_ACCOUNT_RISK_SNAPSHOT"],"live_orders_enabled":False}
        try:
            snap=PortfolioSnapshot(
                mark_price=float(snapshot["mark_price"]), account_equity=float(snapshot["account_equity"]),
                current_position_btc=float(snapshot["current_position_btc"]),
                maintenance_margin_rate=float(snapshot["maintenance_margin_rate"]),
                day_start_equity=float(snapshot["day_start_equity"]), week_start_equity=float(snapshot["week_start_equity"]),
                peak_equity=float(snapshot["peak_equity"]), market_data_age_seconds=float(snapshot.get("market_data_age_seconds", math.inf)),
                websocket_latency_ms=float(snapshot.get("websocket_latency_ms", math.inf)),
                memory_mb=float(snapshot.get("memory_mb", math.inf)), kill_switch=bool(snapshot.get("kill_switch",False)))
            d=evaluate(snap,OrderIntent(float(signed_quantity_btc)),limits)
            return {"verdict":d.verdict.value,"approved_signed_quantity_btc":d.approved_signed_quantity_btc,
                    "reason_codes":list(d.reason_codes),"net_exposure_btc":d.net_exposure_btc,
                    "stress_equity":d.stress_equity,"stress_maintenance_margin":d.stress_maintenance_margin,
                    "stress_headroom_fraction":d.stress_headroom_fraction,"live_orders_enabled":False}
        except (ValueError, TypeError, OverflowError):
            return {"verdict":"REJECTED","approved_signed_quantity_btc":0.0,
                    "reason_codes":["INVALID_ACCOUNT_RISK_SNAPSHOT"],"live_orders_enabled":False}

    def create_parent(self, parent_id: str, *, side: str, quantity_btc: float,
                      child_count: int, snapshot: dict | None, now_ts: float | None = None,
                      limits: RiskLimits = RiskLimits()) -> dict:
        if not parent_id or side not in {"buy","sell"}: raise ValueError("valid parent ID and side required")
        if not math.isfinite(quantity_btc) or quantity_btc <= 0 or not isinstance(child_count,int) or child_count < 1:
            raise ValueError("invalid simulated order sizing")
        now=float(time.time() if now_ts is None else now_ts)
        if not math.isfinite(now) or now <= 0: raise ValueError("invalid timestamp")
        signed=quantity_btc if side=="buy" else -quantity_btc
        risk=self.evaluate_intent(signed_quantity_btc=signed,snapshot=snapshot,limits=limits)
        # Any scale is surfaced explicitly; never silently alter the requested quantity.
        if risk["verdict"] != "APPROVED" or abs(risk["approved_signed_quantity_btc"]-signed)>1e-12:
            self.record("PAPER_INTENT_REJECTED",{"parent_id":parent_id,"risk":risk})
            return {"created":False,"state":"REJECTED","risk":risk,"live_orders_enabled":False}
        risk_json=json.dumps(risk,sort_keys=True,separators=(",",":"))
        with self.db:
            self.db.execute("INSERT INTO simulated_parents VALUES(?,?,?,?,?,?)",
                            (parent_id,side,quantity_btc,now,"PAPER_PENDING",risk_json))
            for i in range(1,child_count+1):
                qty=quantity_btc/child_count if i<child_count else quantity_btc-quantity_btc/child_count*(child_count-1)
                self.db.execute("INSERT INTO simulated_children VALUES(?,?,?,?,?,?,?)",
                                (f"{parent_id}:{i:04d}",parent_id,i,qty,"PENDING",None,None))
            self.db.execute("INSERT INTO paper_events(event_ts,kind,payload_json) VALUES(?,?,?)",
                            (now,"PAPER_PARENT_CREATED",json.dumps({"parent_id":parent_id,"risk":risk},sort_keys=True)))
        return {"created":True,"state":"PAPER_PENDING","parent_id":parent_id,"child_count":child_count,
                "risk":risk,"live_orders_enabled":False}

    def authorize_child(self, parent_id: str, child_id: str, *, snapshot: dict | None,
                        limits: RiskLimits = RiskLimits(), event_ts: float | None = None) -> dict:
        """Re-check the simulated child intent immediately before paper dispatch."""
        row=self.db.execute(
            "SELECT c.*,p.side FROM simulated_children c JOIN simulated_parents p ON p.parent_id=c.parent_id "
            "WHERE c.child_id=? AND c.parent_id=?", (child_id,parent_id)).fetchone()
        if row is None:
            return {"authorized":False,"reason_codes":["UNKNOWN_PAPER_CHILD"],"live_orders_enabled":False}
        if row["state"] != "PENDING":
            return {"authorized":False,"reason_codes":["CHILD_NOT_PENDING"],"live_orders_enabled":False}
        signed=float(row["quantity_btc"]) if row["side"]=="buy" else -float(row["quantity_btc"])
        risk=self.evaluate_intent(signed_quantity_btc=signed,snapshot=snapshot,limits=limits)
        ok=(risk["verdict"]=="APPROVED" and
            abs(float(risk["approved_signed_quantity_btc"])-signed)<=1e-12)
        ts=float(time.time() if event_ts is None else event_ts)
        with self.db:
            if ok:
                self.db.execute("UPDATE simulated_children SET state='RISK_APPROVED' WHERE child_id=? AND state='PENDING'",(child_id,))
            self.db.execute("INSERT INTO paper_events(event_ts,kind,payload_json) VALUES(?,?,?)",
                (ts,"PAPER_CHILD_RISK_CHECK",json.dumps({"parent_id":parent_id,"child_id":child_id,
                    "authorized":ok,"risk":risk},sort_keys=True)))
        return {"authorized":ok,"risk":risk,"reason_codes":risk["reason_codes"],
                "live_orders_enabled":False,"next_state":"RISK_APPROVED" if ok else "BLOCKED"}

    def record(self, kind: str, payload: dict, event_ts: float | None = None):
        ts=float(time.time() if event_ts is None else event_ts)
        if not kind or not math.isfinite(ts): raise ValueError("invalid event")
        with self.db:
            self.db.execute("INSERT INTO paper_events(event_ts,kind,payload_json) VALUES(?,?,?)",
                            (ts,kind,json.dumps(payload,sort_keys=True,allow_nan=False)))

    def journal_mode(self) -> str:
        return str(self.db.execute("PRAGMA journal_mode").fetchone()[0]).lower()

    def close(self): self.db.close()
    def __enter__(self): return self
    def __exit__(self,*args): self.close()
