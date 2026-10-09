"""Continuous validation v1: fail-closed paper evaluation ledger."""
from pathlib import Path
import json, time, math

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"data/processed/institutional_absorption_monitor_v2.jsonl"
OUT=ROOT/"data/processed/continuous_validation_v1.json"
MIN_TRADES=100

def main():
    trades=[]
    if SRC.exists():
        for line in SRC.read_text().splitlines():
            try: row=json.loads(line)
            except Exception: continue
            ev=row.get("event")
            # Monitor v2 writes event fields at the top level. Accept nested
            # events as well so validation remains compatible with older ledgers.
            if isinstance(ev,dict):
                event=ev
            else:
                event=row
            if event.get("event")!="EXIT": continue
            trades.append(event)
    wins=sum(1 for x in trades if float(x.get("pnl",0))>0)
    losses=sum(1 for x in trades if float(x.get("pnl",0))<0)
    gross_win=sum(float(x.get("pnl",0)) for x in trades if float(x.get("pnl",0))>0)
    gross_loss=-sum(float(x.get("pnl",0)) for x in trades if float(x.get("pnl",0))<0)
    pf=(gross_win/gross_loss) if gross_loss else (math.inf if gross_win else 0)
    result={
      "generated_at":time.time(),"sample_size":len(trades),"wins":wins,"losses":losses,
      "win_rate":wins/len(trades) if trades else 0,
      "profit_factor":pf,"net_pnl":sum(float(x.get("pnl",0)) for x in trades),
      "promotion_eligible":False,
      "paper_only":True,"real_orders":False,
      "gate":{"min_trades":MIN_TRADES,"min_win_rate":0.55,"min_profit_factor":1.2,
              "positive_walk_forward_required":True},
      "status":"COLLECTING_EVIDENCE" if len(trades)<MIN_TRADES else "REQUIRES_WALK_FORWARD_REVIEW"
    }
    OUT.write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
if __name__=="__main__": main()
