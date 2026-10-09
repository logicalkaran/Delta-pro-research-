"""Continuous $2->$4 paper challenge monitor. No exchange orders."""
from pathlib import Path
import sys,json,time,signal
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from strategy.predictive_levels_v1 import compute_levels
STATE=ROOT/"data/live_microstructure_state.json"; CANDLES=ROOT/"data/live_candles.json"
OUT=ROOT/"data/processed/micro_challenge_stream_v1.jsonl"; SUMMARY=ROOT/"data/processed/micro_challenge_stream_v1_summary.json"
RUN=True; TICK=.5; HOLD=900; FEE=11.; SLIP=4.; ADV=3.
def stop(*_):
    global RUN; RUN=False
signal.signal(signal.SIGINT,stop); signal.signal(signal.SIGTERM,stop)
def f(x,d=0):
    try:return float(x)
    except:return d
def read(p):
    try:return json.loads(p.read_text())
    except:return None
def write(x):
    OUT.parent.mkdir(parents=True,exist_ok=True)
    with OUT.open("a") as h:h.write(json.dumps(x,separators=(",",":"))+"\n")
def main(seconds=86400):
    global RUN
    started=time.time(); positions={}; stats={"ticks":0,"signals":0,"entries":0,"exits":0}
    print("MICRO CHALLENGE STREAM STARTED | PAPER ONLY | REAL ORDERS OFF",flush=True)
    while RUN and time.time()-started<seconds:
        s=read(STATE); candles=read(CANDLES)
        if not isinstance(s,dict) or not isinstance(candles,list): time.sleep(TICK); continue
        px=f(s.get("order_book",{}).get("mid_price")); fresh=f(s.get("quality",{}).get("fresh_seconds"),999)
        if px<=0 or fresh>2: time.sleep(TICK); continue
        levels=compute_levels(candles,px,s.get("order_book",{})); w5=s.get("windows",{}).get("5",{}); w30=s.get("windows",{}).get("30",{})
        d5=f(w5.get("delta_pct")); d30=f(w30.get("delta_pct")); imb=f(s.get("order_book",{}).get("imbalance_5"))
        ret5=f(s.get("price",{}).get("5",{}).get("return_pct")); now=time.time()
        candidates=[]
        if d5<=-.10 and d30<0 and ret5>-.06 and imb>-.60: candidates.append(("ABSORPTION_LONG","LONG"))
        if d5>=.10 and d30>0 and ret5<.06 and imb<.60: candidates.append(("ABSORPTION_SHORT","SHORT"))
        if levels.nearest_support and abs(px-levels.nearest_support)<=max(levels.atr*.35,px*.0005) and d30<-.05 and ret5>=-.03: candidates.append(("LEVEL_FLOW_LONG","LONG"))
        if levels.nearest_resistance and abs(px-levels.nearest_resistance)<=max(levels.atr*.35,px*.0005) and d30>.05 and ret5<=.03: candidates.append(("LEVEL_FLOW_SHORT","SHORT"))
        if d5>.12 and d30>.04 and ret5>.03: candidates.append(("FLOW_MOMENTUM_LONG","LONG"))
        if d5<-.12 and d30<-.04 and ret5<-.03: candidates.append(("FLOW_MOMENTUM_SHORT","SHORT"))
        stats["ticks"]+=1
        for key,pos in list(positions.items()):
            hit_stop=px<=pos["stop"] if pos["side"]=="LONG" else px>=pos["stop"]; hit_target=px>=pos["target"] if pos["side"]=="LONG" else px<=pos["target"]; timeout=now-pos["opened"]>=HOLD
            if hit_stop or hit_target or timeout:
                reason="STOP" if hit_stop else ("TARGET" if hit_target else "TIMEOUT")
                gross=-pos["risk_bps"] if reason=="STOP" else (pos["risk_bps"]*2 if reason=="TARGET" else ((px-pos["entry"])/pos["entry"]*10000 if pos["side"]=="LONG" else (pos["entry"]-px)/pos["entry"]*10000))
                net=gross-2*(FEE+SLIP+ADV)
                write({"ts":now,"event":"EXIT","strategy":key,"side":pos["side"],"entry":pos["entry"],"exit":px,"reason":reason,"gross_bps":gross,"net_bps":net,"rr":2.0,"regime":levels.regime})
                stats["exits"]+=1; del positions[key]
        for key,side in candidates:
            stats["signals"]+=1
            if key in positions: continue
            atr=max(levels.atr,px*.0008); risk=min(atr,px*.003)
            entry=px; stop_px=entry-risk if side=="LONG" else entry+risk; target=entry+2*risk if side=="LONG" else entry-2*risk
            positions[key]={"side":side,"entry":entry,"stop":stop_px,"target":target,"risk_bps":risk/entry*10000,"opened":now}
            write({"ts":now,"event":"ENTRY","strategy":key,"side":side,"entry":entry,"stop":stop_px,"target":target,"rr":2.0,"regime":levels.regime,"d5":d5,"d30":d30,"imbalance":imb,"fresh":fresh,"paper_only":True})
            stats["entries"]+=1
        time.sleep(TICK)
    SUMMARY.write_text(json.dumps({**stats,"duration_s":time.time()-started,"open_positions":len(positions),"paper_only":True,"real_orders":False},indent=2))
    print(json.dumps({**stats,"open_positions":len(positions),"paper_only":True,"real_orders":False},indent=2),flush=True)
if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser(); p.add_argument("--seconds",type=int,default=86400); main(p.parse_args().seconds)
