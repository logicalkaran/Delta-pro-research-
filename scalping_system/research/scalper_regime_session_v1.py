"""Regime/session attribution for live paper scalper exits.

This is descriptive only: it does not optimize or modify production strategy code.
"""
from __future__ import annotations
import json,time,datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
J=ROOT/"data/processed/scalper_portfolio_paper_v1.jsonl"
O=ROOT/"data/processed/scalper_regime_session_report_v1.json"

def main():
    groups={}
    if J.exists():
        for line in J.read_text().splitlines():
            try:r=json.loads(line)
            except:continue
            if r.get("event")!="PAPER_EXIT":continue
            ts=float(r.get("ts",0));dt=datetime.datetime.fromtimestamp(ts,datetime.timezone.utc)
            # India session bucket; UTC+5:30.
            hour=(dt.hour*60+dt.minute+330)%1440//60
            session="00-06" if hour<6 else "06-12" if hour<12 else "12-18" if hour<18 else "18-24"
            key=(r.get("strategy","UNKNOWN"),session)
            d=groups.setdefault(key,{"trades":0,"wins":0,"net_bps":0.0})
            n=float(r.get("net_bps",0));d["trades"]+=1;d["wins"]+=n>0;d["net_bps"]+=n
    rows=[]
    for (strategy,session),d in groups.items():
        d["win_rate"]=d["wins"]/d["trades"] if d["trades"] else 0
        d["avg_net_bps"]=d["net_bps"]/d["trades"] if d["trades"] else 0
        rows.append({"strategy":strategy,"ist_session":session,**d})
    rows.sort(key=lambda x:(x["trades"]>=30,x["avg_net_bps"]),reverse=True)
    result={"generated_at":time.time(),"status":"PAPER_ANALYSIS_ONLY","real_orders":False,"rows":rows}
    O.write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
if __name__=="__main__":main()
