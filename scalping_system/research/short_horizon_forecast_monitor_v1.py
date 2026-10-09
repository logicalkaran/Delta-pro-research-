"""Continuous 1-5m forecast journal/calibration. Paper-only."""
from pathlib import Path
import json,time,signal
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from strategy.short_horizon_predictor_v1 import predict
from strategy.predictive_levels_v1 import compute_levels
STATE=ROOT/"data/live_microstructure_state.json"; CANDLES=ROOT/"data/live_candles.json"
OUT=ROOT/"data/processed/short_horizon_forecasts_v1.jsonl"
RUN=True
def stop(*_):
 global RUN; RUN=False
signal.signal(signal.SIGINT,stop); signal.signal(signal.SIGTERM,stop)
def read(p):
 try:return json.loads(p.read_text())
 except:return None
def emit(x):
 OUT.parent.mkdir(parents=True,exist_ok=True)
 with OUT.open("a") as h:h.write(json.dumps(x,separators=(",",":"))+"\n")
def main(seconds=86400):
 started=time.time(); last=None
 while RUN and time.time()-started<seconds:
  s=read(STATE); c=read(CANDLES)
  if not isinstance(s,dict) or not isinstance(c,list): time.sleep(.5); continue
  ob=s.get("order_book",{}); px=float(ob.get("mid_price",0) or 0)
  if px<=0: time.sleep(.5); continue
  ts=int(time.time()); key=(ts//10)
  if key!=last:
   lv=compute_levels(c,px,ob); pred=predict(c,lv,s)
   emit({"issued_at":ts,"price":pred.price,"forecasts":[x.__dict__ for x in pred.forecasts],
         "support":list(pred.support),"resistance":list(pred.resistance),"regime":pred.regime,
         "execution_bias":pred.execution_bias,"confidence":pred.confidence,
         "data_quality":pred.data_quality,"paper_only":True})
   last=key
  time.sleep(.5)
 print("FORECAST_MONITOR_STOPPED",flush=True)
if __name__=="__main__":
 import argparse
 ap=argparse.ArgumentParser(); ap.add_argument("--seconds",type=int,default=86400)
 main(ap.parse_args().seconds)
