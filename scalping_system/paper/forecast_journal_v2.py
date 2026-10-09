import json,os,time,sys
ROOT=os.path.expanduser("~/btc_fisher_trader");SRC=ROOT+"/data/live_microstructure_state.json";OUT=ROOT+"/data/processed/forecast_journal_v2.jsonl";PEND=ROOT+"/data/processed/forecast_pending_v2.json";SUM=ROOT+"/data/processed/forecast_calibration_v2.json"
sys.path.insert(0,ROOT)
from strategy.market_forecaster_v1 import forecast
def load(p,d):
 try:
  with open(p) as f:return json.load(f)
 except:return d
def save(p,x):
 os.makedirs(os.path.dirname(p),exist_ok=True);tmp=p+".tmp"
 with open(tmp,"w") as f:json.dump(x,f,separators=(",",":"))
 os.replace(tmp,p)
def main():
 s=load(SRC,{}) or {};now=time.time();state_ts=float(s.get("timestamp",0));px=float(s.get("order_book",{}).get("mid_price",0) or 0)
 stale=now-state_ts>5
 if px<=0 or stale:return
 pending=load(PEND,[]) or [];keep=[];completed=[]
 for r in pending:
  if now-r["ts"]<r["horizon_s"]:keep.append(r);continue
  ret=(px/r["entry_price"]-1)*10000
  r.update(resolved_ts=now,resolved_price=px,elapsed_s=round(now-r["ts"],3),return_bps=round(ret,4))
  r["hit"]=int((r["direction"]=="UP" and ret>0) or (r["direction"]=="DOWN" and ret<0) or (r["direction"]=="FLAT" and abs(ret)<=1))
  completed.append(r)
 if completed:
  with open(OUT,"a") as f:
   for r in completed:f.write(json.dumps(r,separators=(",",":"))+"\n")
 last=float(load(PEND+"._last",0) or 0)
 if now-last>=10:
  z=forecast(s)
  for h,k in ((30,"horizon_30s"),(60,"horizon_60s")):
   keep.append({"ts":now,"horizon_s":h,"entry_price":px,"direction":z[k]["direction"],"strength":z[k]["strength"],"raw_score":z["raw_score"],"drivers":z["drivers"],"vetoes":z["vetoes"],"spread_bps":z["spread_bps"],"calibration":"UNVALIDATED","paper_only":True,"order_submission":False})
  save(PEND+"._last",now)
 save(PEND,keep)
 rows=[]
 try:
  with open(OUT) as f:rows=[json.loads(x) for x in f if x.strip()]
 except:pass
 stats={}
 for h in (30,60):
  a=[r for r in rows if r.get("horizon_s")==h and r.get("hit") is not None];active=[r for r in a if r.get("direction") in ("UP","DOWN")]
  stats[str(h)]={"n":len(a),"active_n":len(active),"accuracy":round(sum(r["hit"] for r in a)/len(a),4) if a else None,"active_accuracy":round(sum(r["hit"] for r in active)/len(active),4) if active else None,"avg_return_bps":round(sum(r["return_bps"] for r in a)/len(a),4) if a else None,"up_n":sum(r["direction"]=="UP" for r in a),"down_n":sum(r["direction"]=="DOWN" for r in a),"flat_n":sum(r["direction"]=="FLAT" for r in a)}
 save(SUM,{"updated_ts":now,"status":"UNVALIDATED","stats":stats,"minimum_validation_n":100,"data_freshness_required_s":5,"paper_only":True,"order_submission":False})
if __name__=="__main__":main()
