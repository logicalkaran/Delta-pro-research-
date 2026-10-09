"""Evidence-only promotion gate. Never enables or submits real orders."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SUMMARY=ROOT/"data/processed/live_execution_paper_v2_summary.json"
JOURNAL=ROOT/"data/processed/live_execution_paper_v2.jsonl"
OUT=ROOT/"data/processed/live_execution_promotion_gate.json"
MIN_TRADES=100
MIN_WIN_RATE=.52
MIN_PF=1.20
MIN_AVG_NET_BPS=.50

def events():
    if not JOURNAL.exists(): return []
    out=[]
    for line in JOURNAL.read_text().splitlines():
        try: out.append(json.loads(line))
        except: pass
    return out

def main():
    ev=events(); exits=[x for x in ev if x.get("event")=="PAPER_EXIT"]
    fills=[x for x in ev if x.get("event")=="MAKER_FILL"]
    posted=[x for x in ev if x.get("event")=="POST_ONLY_ENTRY"]
    candidates=[x for x in ev if x.get("event")=="ABSREV_CANDIDATE"]
    s=json.loads(SUMMARY.read_text()) if SUMMARY.exists() else {}
    checks={
      "paper_engine_only": True,
      "real_orders_disabled": s.get("real_orders",False) is False if s else True,
      "entry_model": s.get("entry_model","POST_ONLY_QUEUE_SIM")=="POST_ONLY_QUEUE_SIM",
      "exit_model": s.get("exit_model","EXECUTABLE_TAKER_CONSERVATIVE")=="EXECUTABLE_TAKER_CONSERVATIVE",
      "minimum_completed_trades": len(exits)>=MIN_TRADES,
      "minimum_net_edge": float(s.get("avg_net_bps",-999))>=MIN_AVG_NET_BPS if s else False,
      "minimum_profit_factor": float(s.get("profit_factor",-1))>=MIN_PF if s else False,
      "minimum_win_rate": float(s.get("win_rate",-1))>=MIN_WIN_RATE if s else False,
    }
    reasons=[k for k,v in checks.items() if not v]
    result={
      "status":"BLOCKED","promotion_allowed":False,"real_orders":False,
      "checks":checks,"blocking_reasons":reasons,
      "candidate_count":len(candidates),"posted_count":len(posted),
      "maker_fill_count":len(fills),"completed_trade_count":len(exits),
      "post_to_fill_rate":len(fills)/len(posted) if posted else 0.0,
      "candidate_to_fill_rate":len(fills)/len(candidates) if candidates else 0.0,
      "minimums":{"completed_trades":MIN_TRADES,"win_rate":MIN_WIN_RATE,"profit_factor":MIN_PF,"avg_net_bps":MIN_AVG_NET_BPS},
      "statement":"Evidence gate only. It cannot place, enable, or authorize exchange orders."
    }
    OUT.write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
if __name__=="__main__": main()
