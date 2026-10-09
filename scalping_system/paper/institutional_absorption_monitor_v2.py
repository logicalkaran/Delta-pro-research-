"""Continuous paper monitor for institutional absorption.

Execution model is deliberately conservative:
- signal is observed on a completed 1m candle;
- entry occurs on the next 1m candle open, not at the signal price;
- configurable slippage + adverse-selection cost is applied;
- if stop and target are both touched in one candle, stop wins;
- time-stop closes after max_hold_minutes;
- no exchange order API is called.
"""
from __future__ import annotations
import json, os, time, urllib.parse, urllib.request
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from strategy.institutional_absorption_v1 import evaluate, AbsorptionConfig
from strategy.edge_selector_v1 import score_signal, EdgeConfig

STATE=ROOT/"data/processed/institutional_absorption_monitor_v2_state.json"
EVENTS=ROOT/"data/processed/institutional_absorption_monitor_v2.jsonl"
TELEMETRY=ROOT/"data/processed/institutional_absorption_telemetry_v1.jsonl"

class PaperConfig:
    poll_seconds=float(os.getenv("ABS_POLL_SECONDS","20"))
    fee_bps=float(os.getenv("ABS_FEE_BPS","5.5"))
    slippage_bps=float(os.getenv("ABS_SLIPPAGE_BPS","2.0"))
    adverse_bps=float(os.getenv("ABS_ADVERSE_BPS","1.5"))
    max_hold_minutes=int(os.getenv("ABS_MAX_HOLD_MINUTES","30"))
    starting_equity=float(os.getenv("ABS_STARTING_EQUITY","100000"))

CFG=PaperConfig()

def get(url,timeout=5,retries=2):
    req=urllib.request.Request(url,headers={"User-Agent":"btc-absorption-paper-v2/1.0","Accept":"application/json"})
    last=None
    for attempt in range(retries+1):
        try:
            with urllib.request.urlopen(req,timeout=timeout) as r:
                return json.loads(r.read().decode())
        except (urllib.error.URLError, TimeoutError) as exc:
            last=exc
            if attempt < retries:
                time.sleep(0.5*(attempt+1))
    raise last

def candles(res):
    now=int(time.time())
    seconds=60 if res=="1m" else 300
    start=now-(300*seconds)
    q=urllib.parse.urlencode({"resolution":res,"symbol":"BTCUSD","start":start,"end":now})
    d=get("https://api.india.delta.exchange/v2/history/candles?"+q)
    if not d.get("success",True):raise RuntimeError("candle feed unsuccessful")
    return sorted(d.get("result",[]),key=lambda x:x.get("time",0))

def load_json(p,default):
    try:return json.loads(p.read_text())
    except:return default

def save_json(p,obj):
    p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(obj,indent=2))

def latest_oi_change():
    p=ROOT/"data/processed/cross_venue_btc_v43.jsonl"
    if not p.exists():return 0.0
    rows=[]
    with p.open(errors="ignore") as f:
        for line in f.readlines()[-40:]:
            try:rows.append(json.loads(line))
            except:pass
    by={}
    for row in rows:
        ts=int(row.get("epoch_ms",0))
        for v in row.get("comparison",{}).get("venues",[]):
            if v.get("venue") in ("binance","bybit"):
                oi=float(v.get("open_interest") or 0)
                if oi>0:by.setdefault(v["venue"],[]).append((ts,oi))
    changes=[]
    for vals in by.values():
        vals.sort()
        if len(vals)<2:continue
        latest_t,latest=vals[-1]
        older=next((v for t,v in reversed(vals[:-1]) if latest_t-t>=15000),vals[0][1])
        if older>0:changes.append((latest/older-1)*100)
    return sum(changes)/len(changes) if changes else 0.0

def micro():
    return load_json(ROOT/"data/live_microstructure_state.json",{})

def cost_bps():
    return CFG.fee_bps*2 + CFG.slippage_bps*2 + CFG.adverse_bps*2

def fill(price,side,bps):
    x=price*(1+bps/10000)
    return x if side=="LONG" else price*(1-bps/10000)

def init_state():
    return {"started_at":int(time.time()),"equity":CFG.starting_equity,"realized_pnl":0.0,
            "evaluations":0,"signals":0,"wins":0,"losses":0,"timeouts":0,
            "consecutive_losses":0,"position":None,"last_signal_candle":None,"last_entry_candle":None}

def settle_position(st,rows):
    pos=st.get("position")
    if not pos:return
    last=rows[-1]
    last_time=int(last.get("time",0))
    entry_candle=int(pos["entry_candle"])
    hold=max(0,(last_time-entry_candle)//60)
    action=pos["action"]; stop=pos["stop"]; target=pos["target"]
    # Track maximum favorable/adverse excursion from the conservative entry fill.
    entry=pos["entry"]
    for c in rows:
        t=int(c.get("time",0))
        if t<=entry_candle:continue
        h=float(c.get("high"));l=float(c.get("low"))
        hit_stop=(l<=stop) if action=="LONG" else (h>=stop)
        hit_target=(h>=target) if action=="LONG" else (l<=target)
        # Conservative ordering when both occur in the same bar.
        if hit_stop or hit_target:
            reason="STOP" if hit_stop else "TARGET"
            raw_exit=stop if hit_stop else target
            exit_px=fill(raw_exit,action,CFG.adverse_bps+CFG.slippage_bps)
            entry=pos["entry"]
            qty=pos["quantity"]
            gross=(exit_px-entry)*qty if action=="LONG" else (entry-exit_px)*qty
            fees=(entry+exit_px)*qty*CFG.fee_bps/10000
            pnl=gross-fees
            st["realized_pnl"]+=pnl
            st["equity"]+=pnl
            if pnl>0:
                st["wins"]+=1; st["consecutive_losses"]=0
            else:
                st["losses"]+=1; st["consecutive_losses"]=int(st.get("consecutive_losses",0))+1
            st["position"]=None
            return {"event":"EXIT","reason":reason,"pnl":pnl,"entry":entry,"exit":exit_px,"hold_minutes":max(1,(t-entry_candle)//60),"action":action,"confidence":pos.get("confidence",0.0),"regime":pos.get("regime")}
        if (t-entry_candle)//60>=CFG.max_hold_minutes:
            raw_exit=float(c.get("close"))
            exit_px=fill(raw_exit,action,CFG.adverse_bps+CFG.slippage_bps)
            entry=pos["entry"];qty=pos["quantity"]
            gross=(exit_px-entry)*qty if action=="LONG" else (entry-exit_px)*qty
            fees=(entry+exit_px)*qty*CFG.fee_bps/10000
            pnl=gross-fees
            st["realized_pnl"]+=pnl;st["equity"]+=pnl;st["timeouts"]+=1
            if pnl>0:
                st["wins"]+=1; st["consecutive_losses"]=0
            else:
                st["losses"]+=1; st["consecutive_losses"]=int(st.get("consecutive_losses",0))+1
            st["position"]=None
            return {"event":"EXIT","reason":"TIMEOUT","pnl":pnl,"entry":entry,"exit":exit_px,"hold_minutes":max(1,(t-entry_candle)//60),"action":action,"confidence":pos.get("confidence",0.0),"regime":pos.get("regime")}
    return None

def evaluate_once(st):
    m=micro(); c1=candles("1m"); c5=candles("5m")
    if len(c1)<20:return {"event":"SKIP","reason":"INSUFFICIENT_CANDLES"}
    st["evaluations"]+=1
    closed=c1[:-1]  # never use the currently forming candle
    signal_candle=int(closed[-1].get("time",0))
    exit_event=settle_position(st,closed)
    if exit_event:return exit_event
    if st.get("position") is not None:return {"event":"HOLD","position":st["position"]}
    pending=st.get("pending_entry")
    if pending:
        pending_signal=int(pending.get("signal_candle",0))
        if signal_candle>pending_signal:
            entry_raw=float(closed[-1].get("open") or closed[-1].get("close"))
            entry=fill(entry_raw,pending["action"],CFG.slippage_bps+CFG.adverse_bps)
            st["position"]={"action":pending["action"],"signal_candle":pending_signal,
                            "entry_candle":signal_candle,"entry":entry,"stop":pending["stop"],
                            "target":pending["target"],"quantity":1.0,
                            "expected_rr":pending["expected_rr"],"confidence":pending["confidence"],
                            "regime":pending.get("regime"),"entry_cost_bps":CFG.slippage_bps+CFG.adverse_bps}
            st["pending_entry"]=None
            return {"event":"ENTRY","action":pending["action"],"entry":entry,
                    "stop":pending["stop"],"target":pending["target"],"rr":pending["expected_rr"],
                    "confidence":pending["confidence"],"signal_candle":pending_signal,
                    "entry_candle":signal_candle}
    if st.get("last_signal_candle")==signal_candle:return {"event":"DUPLICATE_SIGNAL_BAR"}
    st["last_signal_candle"]=signal_candle
    poc=None
    p=ROOT/"data/processed/predictive_levels_live.json"
    if p.exists():
        try:poc=float(load_json(p,{}).get("poc") or 0) or None
        except:poc=None
    oi_change=latest_oi_change()
    sig=evaluate(m,closed[-240:],c5[-120:],oi_change_pct=oi_change,poc=poc,cfg=AbsorptionConfig())
    last_bar=closed[-1]
    prior=closed[:-1]
    prev_low=min(float(c.get("low",0) or 0) for c in prior[-10:]) if prior else 0.0
    prev_high=max(float(c.get("high",0) or 0) for c in prior[-10:]) if prior else 0.0
    bar_high=float(last_bar.get("high",0) or 0)
    bar_low=float(last_bar.get("low",0) or 0)
    bar_close=float(last_bar.get("close",0) or 0)
    bar_range=max(bar_high-bar_low,0.0)
    telemetry={
        "signal_candle":signal_candle,
        "price":float(m.get("order_book",{}).get("mid_price") or 0),
        "regime":m.get("regime"),
        "cvd_30s_pct":float(m.get("cvd_slope_30s_pct",m.get("windows",{}).get("30",{}).get("delta_pct",0)) or 0),
        "oi_change_pct":oi_change,
        "spread":float(m.get("order_book",{}).get("spread") or 0),
        "spread_bps":(float(m.get("order_book",{}).get("spread") or 0)/max(float(m.get("order_book",{}).get("mid_price") or 1),1))*10000,
        "fresh_seconds":float(m.get("quality",{}).get("fresh_seconds") or 999),
        "imbalance_5":float(m.get("order_book",{}).get("imbalance_5") or 0),
        "imbalance_10":float(m.get("order_book",{}).get("imbalance_10") or 0),
        "new_1m_low":bool(bar_low < prev_low) if prev_low else False,
        "new_1m_high":bool(bar_high > prev_high) if prev_high else False,
        "long_rejection":max(0.0,(bar_close-bar_low)/bar_range) if bar_range else 0.0,
        "short_rejection":max(0.0,(bar_high-bar_close)/bar_range) if bar_range else 0.0,
        "bar_range":bar_range,
        "atr":float(sig.atr),
        "range_atr":(bar_range/float(sig.atr)) if sig.atr else 0.0,
        "five_min_bias":sig.five_min_bias,
        "action":sig.action,
        "confidence":sig.confidence,
        "rr":sig.rr,
        "valid":bool(sig.valid),
        "reasons":list(sig.reason)
    }
    log_telemetry(telemetry)
    if not sig.valid:return {"event":"NO_TRADE","action":sig.action,"reason":list(sig.reason),"confidence":sig.confidence}
    equity=max(float(st.get("equity",CFG.starting_equity)),1e-9)
    daily_loss=max(0.0,-float(st.get("realized_pnl",0.0))) / equity
    edge=score_signal(sig,m,oi_change,EdgeConfig(),daily_loss,float(st.get("consecutive_losses",0)))
    if not edge.allowed:
        return {"event":"EDGE_REJECT","action":"NO_TRADE","edge_score":edge.score,"reason":list(edge.reasons),"confidence":sig.confidence,"rr":sig.rr}
    # Signal is valid, but fill is intentionally delayed to the next candle.
    # Queue the accepted signal. Never retrospectively assume the current
    # forming candle's open was fillable; resolve on the next completed candle.
    st["signals"]+=1
    st["pending_entry"]={"action":sig.action,"signal_candle":signal_candle,
                         "stop":sig.stop,"target":sig.target,"expected_rr":sig.rr,
                         "confidence":sig.confidence,"regime":m.get("regime"),
                         "queued_at":int(time.time())}
    return {"event":"EDGE_ACCEPT","action":sig.action,"side":sig.action,
            "stop":sig.stop,"target":sig.target,"rr":sig.rr,"confidence":sig.confidence,
            "signal_candle":signal_candle,"entry_pending":True}

def log_telemetry(event):
    TELEMETRY.parent.mkdir(parents=True,exist_ok=True)
    with TELEMETRY.open("a") as f:f.write(json.dumps({"ts":int(time.time()),**event},separators=(",",":"))+"\n")

def log_event(event):
    EVENTS.parent.mkdir(parents=True,exist_ok=True)
    with EVENTS.open("a") as f:f.write(json.dumps({"ts":int(time.time()),**event},separators=(",",":"))+"\n")

def summary(st):
    total=st["wins"]+st["losses"]
    return {"updated_at":int(time.time()),"equity":st["equity"],"realized_pnl":st["realized_pnl"],
            "evaluations":st["evaluations"],"signals":st["signals"],"closed_trades":total,
            "wins":st["wins"],"losses":st["losses"],"timeouts":st["timeouts"],
            "win_rate":st["wins"]/total if total else 0.0,"cost_model_bps_roundtrip":cost_bps(),
            "paper_only":True,"real_orders":False,"position":st.get("position")}

def run_forever():
    st=load_json(STATE,init_state())
    while True:
        try:
            event=evaluate_once(st);log_event(event)
            save_json(STATE,st)
            s=summary(st)
            print(json.dumps({"event":event,"summary":s},separators=(",",":")),flush=True)
        except Exception as e:
            event={"event":"ERROR","error":type(e).__name__+":"+str(e)[:160]}
            log_event(event);print(json.dumps(event,separators=(",",":")),flush=True)
        time.sleep(CFG.poll_seconds)

if __name__=="__main__":run_forever()
