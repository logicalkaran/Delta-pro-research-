import sqlite3
from research.microstructure_paper_ledger import PaperLedger
from risk.orchestration_oracle import RiskLimits

def valid_snapshot():
    return {"mark_price":60000,"account_equity":10000,"current_position_btc":0,
      "maintenance_margin_rate":.0025,"day_start_equity":10000,"week_start_equity":10000,
      "peak_equity":10000,"market_data_age_seconds":.2,"websocket_latency_ms":30,"memory_mb":200}

def test_missing_risk_state_fails_closed(tmp_path):
    with PaperLedger(tmp_path/"paper.sqlite") as ledger:
        r=ledger.create_parent("x",side="buy",quantity_btc=.001,child_count=2,snapshot=None,now_ts=100)
        assert not r["created"] and r["risk"]["verdict"]=="REJECTED"
        assert ledger.journal_mode()=="wal"

def test_wal_parent_and_children_persist(tmp_path):
    p=tmp_path/"paper.sqlite"
    with PaperLedger(p) as ledger:
        r=ledger.create_parent("p1",side="buy",quantity_btc=.001,child_count=3,snapshot=valid_snapshot(),now_ts=100)
        assert r["created"] and not r["live_orders_enabled"]
        assert ledger.db.execute("select count(*) from simulated_children where parent_id='p1'").fetchone()[0]==3
    with sqlite3.connect(p) as db:
        assert db.execute("select state from simulated_parents where parent_id='p1'").fetchone()[0]=="PAPER_PENDING"

def test_risk_oracle_blocks_excess_exposure(tmp_path):
    with PaperLedger(tmp_path/"paper.sqlite") as ledger:
        r=ledger.create_parent("too-big",side="buy",quantity_btc=.1,child_count=2,snapshot=valid_snapshot(),now_ts=100,
            limits=RiskLimits(max_net_exposure_btc=.001))
        assert not r["created"] and r["risk"]["verdict"] in {"SCALED","REJECTED"}

def test_incomplete_snapshot_rejected(tmp_path):
    with PaperLedger(tmp_path/"paper.sqlite") as ledger:
        r=ledger.evaluate_intent(signed_quantity_btc=.001,snapshot={"mark_price":60000})
        assert r["verdict"]=="REJECTED" and r["approved_signed_quantity_btc"]==0

def test_each_paper_child_requires_fresh_risk_approval(tmp_path):
    with PaperLedger(tmp_path/"paper.sqlite") as ledger:
        made=ledger.create_parent("child-parent",side="buy",quantity_btc=.001,child_count=2,
                                  snapshot=valid_snapshot(),now_ts=100)
        assert made["created"]
        blocked=ledger.authorize_child("child-parent","child-parent:0001",snapshot=None,event_ts=101)
        assert not blocked["authorized"] and blocked["live_orders_enabled"] is False
        ok=ledger.authorize_child("child-parent","child-parent:0002",snapshot=valid_snapshot(),event_ts=102)
        assert ok["authorized"] and ok["next_state"]=="RISK_APPROVED"
        duplicate=ledger.authorize_child("child-parent","child-parent:0002",snapshot=valid_snapshot(),event_ts=103)
        assert not duplicate["authorized"] and "CHILD_NOT_PENDING" in duplicate["reason_codes"]
