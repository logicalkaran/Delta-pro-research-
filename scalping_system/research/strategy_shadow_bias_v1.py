"""Paper-only shadow evaluator for bias-conflicted candidates."""
from pathlib import Path
import json,time,signal,argparse
ROOT=Path(__file__).resolve().parents[1]; STATE=ROOT/"data/live_microstructure_state.json"; OUT=ROOT/"data/processed/strategy_shadow_bias_v1.jsonl"
RUN=True; HOLD=900; Q=.001; COST_BPS=12
def stop(*_):
 global RUN; RUN=False
signal.signal(signal.SIGINT,stop); signal.signal(signal.SIGTERM,stop)
def read(p):
 try:return json.loads(p.read_text())
 except:return None
def f(x,d=0):
 try:return float(x)
 except:return d
def emit(x):
 OUT.parent.mkdir(parents=True,exist_ok=True)
 with OUT.open("a") as h:h.write(json.dumps(x,separators=(",",":"))+"\n")
def main(seconds=86400):
 global RUN
 started=time.time(); open_pos=[]
 while RUN and time.time()-started<seconds:
  s=read(STATE)
  if not isinstance(s,dict): time.sleep(.5); continue
  ob=s.get("order_book",{}); px=f(ob.get("mid_price")); fresh=f(s.get("quality",{}).get("fresh_seconds"),999)
  if px<=0 or fresh>2: time.sleep(.5); continue
  now=time.time()
  for pos in open_pos[:]:
   stop_hit=px<=pos["stop"] if pos["side"]=="LONG" else px>=pos["stop"]
   target_hit=px>=pos["target"] if pos["side"]=="LONG" else px<=pos["target"]
   timeout=now-pos["ts"]>=HOLD
   if not(stop_hit or target_hit or timeout): continue
   reason="STOP" if stop_hit else ("TARGET" if target_hit else "TIMEOUT")
   gross=(px-pos["entry"])*Q if pos["side"]=="LONG" else (pos["entry"]-px)*Q
   cost=(pos["entry"]+px)*Q*COST_BPS/10000
   emit({**pos,"event":"SHADOW_EXIT","exit":px,"reason":reason,"gross_pnl_usd":gross,"cost_usd":cost,"net_pnl_usd":gross-cost,"duration_s":now-pos["ts"],"paper_only":True})
   open_pos.remove(pos)
  d5=f(s.get("windows",{}).get("5",{}).get("delta_pct")); d30=f(s.get("windows",{}).get("30",{}).get("delta_pct")); ret5=f(s.get("price",{}).get("5",{}).get("return_pct"))
  bias="BULLISH" if d5>0 else ("BEARISH" if d5<0 else "NEUTRAL")
  candidates=[]
  if d5<=-.10 and d30<0 and ret5>-.06: candidates.append(("ABSORPTION_LONG","LONG"))
  if d5>=.10 and d30>0 and ret5<.06: candidates.append(("ABSORPTION_SHORT","SHORT"))
  for strategy,side in candidates:
   desired="BULLISH" if side=="LONG" else "BEARISH"
   if bias==desired: continue
   if any(x["strategy"]==strategy for x in open_pos): continue
   risk=max(px*.0008,px*.0005); stop_px=px-risk if side=="LONG" else px+risk; target=px+2.5*risk if side=="LONG" else px-2.5*risk
   pos={"ts":now,"event":"SHADOW_ENTRY","strategy":strategy,"side":side,"entry":px,"stop":stop_px,"target":target,"bias":bias,"d5":d5,"d30":d30}
   emit({**pos,"paper_only":True}); open_pos.append(pos)
  time.sleep(.5)
 print(json.dumps({"status":"STOPPED","open_shadow":len(open_pos),"paper_only":True},indent=2),flush=True)
if __name__=="__main__":
 ap=argparse.ArgumentParser(); ap.add_argument("--seconds",type=int,default=86400); main(ap.parse_args().seconds)
