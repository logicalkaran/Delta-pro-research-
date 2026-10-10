"""V4.5 divergence-event engine. Research only."""
import json,os
from datetime import datetime,timezone
IN="data/processed/cross_venue_btc_v43.jsonl"
OUT="data/processed/cross_venue_v45_events.jsonl"
THRESH=2.0
EXIT=0.75
MIN_DUR=2

def load():
    rows=[]
    try:
        with open(IN) as f:
            for line in f:
                try:
                    r=json.loads(line)
                    if r.get("comparison",{}).get("valid") and r.get("venues_ok",0)>=2:
                        rows.append(r)
                except: pass
    except FileNotFoundError: pass
    return rows

def events(rows):
    out=[]; cur=None
    for r in rows:
        e=r.get("edge_v42",{}); s=float(e.get("spread_bps") or 0)
        if s>=THRESH and e.get("leader") and e.get("lagger"):
            key=(e["leader"],e["lagger"])
            if cur is None or cur["key"]!=key:
                if cur and cur["samples"]>=MIN_DUR: out.append(cur)
                cur={"key":key,"start":r["epoch_ms"],"end":r["epoch_ms"],
                     "max_spread":s,"samples":1,"start_price":None}
                for v in r["comparison"]["venues"]:
                    if v["venue"]=="delta": cur["start_price"]=v["price"]
            else:
                cur["end"]=r["epoch_ms"]; cur["samples"]+=1; cur["max_spread"]=max(cur["max_spread"],s)
        elif cur and s<=EXIT:
            if cur["samples"]>=MIN_DUR: out.append(cur)
            cur=None
    if cur and cur["samples"]>=MIN_DUR: out.append(cur)
    for x in out:
        x["duration_s"]=(x["end"]-x["start"])/1000
    return out

rows=load(); ev=events(rows)
os.makedirs(os.path.dirname(OUT),exist_ok=True)
with open(OUT,"w") as f:
    for e in ev: f.write(json.dumps(e,separators=(",",":"))+"\n")
print(json.dumps({"samples":len(rows),"events":len(ev),
                  "events_2bps_plus":[{"duration_s":e["duration_s"],"max_spread_bps":e["max_spread"],"leader":e["key"][0],"lagger":e["key"][1]} for e in ev]},indent=2))
