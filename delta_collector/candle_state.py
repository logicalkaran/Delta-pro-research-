"""Rolling 1-minute OHLC builder from Delta trade events."""
from __future__ import annotations
import json, os, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; STATE=ROOT/"data/live_candles.json"; MAX=240

def _load():
    if not STATE.exists(): return []
    try: return json.loads(STATE.read_text())
    except Exception: return []

def update(message):
    if not isinstance(message,dict) or message.get("type")!="trades": return
    try: price=float(message["p"]); ts=int(float(message.get("ts") or message.get("t")))/1000000
    except (TypeError,ValueError,KeyError): return
    minute=int(ts//60*60); rows=_load()
    if rows and rows[-1]["timestamp"]==minute:
        c=rows[-1]; c["high"]=max(c["high"],price); c["low"]=min(c["low"],price); c["close"]=price; c["volume"]+=float(message.get("s",0)); c["trades"]+=1
    else:
        rows.append({"timestamp":minute,"open":price,"high":price,"low":price,"close":price,"volume":float(message.get("s",0)),"trades":1})
        rows=rows[-MAX:]
    tmp=STATE.with_suffix(".tmp"); tmp.write_text(json.dumps(rows,separators=(",",":")),encoding="utf-8"); os.replace(tmp,STATE)
