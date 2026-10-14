"""Build a durable report from the $2->$4 Delta paper contest ledger."""
from pathlib import Path
import json,collections,time
ROOT=Path(__file__).resolve().parents[1]
LOG=ROOT/"data/processed/micro_challenge_stream_v2.jsonl"
OUT=ROOT/"data/processed/micro_challenge_ledger_v1.json"
def main():
    events=[]
    if LOG.exists():
        for line in LOG.read_text().splitlines():
            try: events.append(json.loads(line))
            except: pass
    exits=[e for e in events if e.get("event")=="EXIT"]
    entries=[e for e in events if e.get("event")=="ENTRY"]
    rejects=[e for e in events if e.get("event")=="REJECT"]
    pnl=sum(float(e.get("net_pnl_usd",0)) for e in exits)
    wins=sum(float(e.get("net_pnl_usd",0))>0 for e in exits)
    losses=sum(float(e.get("net_pnl_usd",0))<=0 for e in exits)
    by_strategy={}
    for e in exits:
        k=e.get("strategy","UNKNOWN"); x=by_strategy.setdefault(k,{"trades":0,"wins":0,"losses":0,"net_pnl_usd":0.0})
        x["trades"]+=1; x["wins"]+=int(float(e.get("net_pnl_usd",0))>0); x["losses"]+=int(float(e.get("net_pnl_usd",0))<=0); x["net_pnl_usd"]+=float(e.get("net_pnl_usd",0))
    rejection=collections.Counter(e.get("reason","UNKNOWN") for e in rejects)
    result={"updated_at":int(time.time()),"contest":"DELTA_BTCUSD_2_TO_4","leverage":200.0,"quantity_btc":0.001,
            "starting_equity":2.0,"target_equity":4.0,"entry_count":len(entries),"exit_count":len(exits),
            "wins":wins,"losses":losses,"win_rate":(wins/len(exits) if exits else None),
            "realized_pnl_usd":pnl,"equity_marked_from_realized":2.0+pnl,
            "profit_factor":(sum(float(e.get("net_pnl_usd",0)) for e in exits if float(e.get("net_pnl_usd",0))>0)/
                             abs(sum(float(e.get("net_pnl_usd",0)) for e in exits if float(e.get("net_pnl_usd",0))<0))
                             if any(float(e.get("net_pnl_usd",0))<0 for e in exits) else None),
            "by_strategy":by_strategy,"rejection_reasons":rejection.most_common(15),
            "paper_only":True,"real_orders":False}
    OUT.write_text(json.dumps(result,indent=2)); print(json.dumps(result,indent=2))
if __name__=="__main__": main()
