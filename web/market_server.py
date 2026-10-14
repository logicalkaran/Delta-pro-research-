import http.server,json,os,time,urllib.parse,threading
from concurrent.futures import ThreadPoolExecutor
import requests
__import__('sys').path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from strategy.market_forecaster_v1 import forecast
from research.scalper_tracker import record,settle_once,stats as forecast_stats
ROOT=os.path.expanduser("~/btc_fisher_trader"); PORT=8789
CACHE={"ts":0,"data":{},"errors":{},"refresh_ms":0,"perpetuals":[],"perp_ts":0,"forecast_record_ts":0}; LOCK=threading.Lock(); HTTP=requests.Session(); HTTP.headers.update({"Accept":"application/json","User-Agent":"BTC-Professional-Dashboard/3.0"})
def rd(p):
 try:
  with open(ROOT+"/"+p) as f:return json.load(f)
 except:return {}
def perpetuals():
 try:
  r=HTTP.get("https://api.india.delta.exchange/v2/products",params={"contract_types":"perpetual_futures","states":"live","page_size":100},timeout=5); r.raise_for_status(); d=r.json()
  rows=d.get("result",[]) if d.get("success",True) else []
  return sorted([{"id":x.get("id"),"symbol":x.get("symbol"),"underlying":(x.get("underlying_asset") or {}).get("symbol"),"tick_size":x.get("tick_size"),"default_leverage":x.get("default_leverage"),"annualized_funding":x.get("annualized_funding"),"trading_status":x.get("trading_status"),"taker_fee":x.get("taker_commission_rate")} for x in rows],key=lambda x:x.get("symbol") or "")
 except Exception as e:
  return [{"error":type(e).__name__+":"+str(e)[:120]}]
def perp_tickers():
 try:
  r=HTTP.get("https://api.india.delta.exchange/v2/tickers",params={"contract_types":"perpetual_futures"},timeout=5); r.raise_for_status(); d=r.json()
  rows=d.get("result",[]) if d.get("success",True) else []
  return {x.get("symbol") : x for x in rows if x.get("symbol")}
 except Exception:return {}
def candles(res,symbol="BTCUSD"):
 now=int(time.time()); start=now-(120*{"1m":60,"5m":300,"1h":3600}[res])
 url="https://api.india.delta.exchange/v2/history/candles?resolution="+res+"&symbol="+urllib.parse.quote(symbol,safe='')+"&start="+str(start)+"&end="+str(now)
 r=HTTP.get(url,timeout=4)
 r.raise_for_status(); d=r.json()
 if not d.get("success",True): raise RuntimeError("Delta API returned unsuccessful response")
 return d.get("result",[])
def ema(vals,n):
 if len(vals)<n:return None
 k=2/(n+1); e=sum(vals[:n])/n
 for v in vals[n:]:e=v*k+e*(1-k)
 return e
def rsi(vals,n=14):
 if len(vals)<=n:return 50
 gains=[];losses=[]
 for a,b in zip(vals[-n-1:-1],vals[-n:]):
  d=b-a;gains.append(max(d,0));losses.append(max(-d,0))
 ag=sum(gains)/n;al=sum(losses)/n
 return 100 if al==0 else 100-(100/(1+ag/al))
def tf_signal(rows):
 rows=sorted(rows,key=lambda x:x.get("time",0)); closes=[float(x["close"]) for x in rows if x.get("close") is not None]
 if len(closes)<55:return {"signal":"HOLD","confidence":0,"reason":"insufficient data","candles":len(closes)}
 e20=ema(closes,20);e50=ema(closes,50);rr=rsi(closes);ret=(closes[-1]/closes[-6]-1)*100;score=0
 score+=1 if closes[-1]>e20 else -1;score+=1 if e20>e50 else -1
 score+=1 if rr>=55 else (-1 if rr<=45 else 0);score+=1 if ret>0.10 else (-1 if ret<-0.10 else 0)
 sig="BUY" if score>=2 else ("SELL" if score<=-2 else "HOLD")
 conf=min(99,50+abs(score)*12+min(abs(rr-50),15))
 return {"signal":sig,"confidence":round(conf),"price":closes[-1],"ema20":e20,"ema50":e50,"rsi14":rr,"return_pct":ret,"score":score,"candles":len(closes)}
def candle_patterns(rows):
 rows=sorted(rows,key=lambda x:x.get("time",0)); out=[]
 for i,r in enumerate(rows):
  try:
   o,h,l,c=map(float,(r["open"],r["high"],r["low"],r["close"])); rng=max(h-l,1e-9); body=abs(c-o); upper=h-max(o,c); lower=min(o,c)-l
   bull=c>o; prev=rows[i-1] if i else None; p=None
   if body/rng<0.12:p="DOJI"
   elif lower>=body*2.0 and upper<=body*0.8 and bull:p="HAMMER"
   elif upper>=body*2.0 and lower<=body*0.8 and not bull:p="SHOOTING_STAR"
   elif prev:
    po,pc=float(prev["open"]),float(prev["close"])
    if bull and pc<po and c>po and o<pc:p="BULLISH_ENGULFING"
    elif (not bull) and pc>po and c<po and o>pc:p="BEARISH_ENGULFING"
   if p: out.append({"time":r.get("time"),"pattern":p,"side":"BUY" if p in ("HAMMER","BULLISH_ENGULFING") else "SELL" if p in ("SHOOTING_STAR","BEARISH_ENGULFING") else "NEUTRAL","price":c})
  except Exception: pass
 return out[-30:]
def chart_markers(rows):
 rows=sorted(rows,key=lambda x:x.get("time",0)); markers=[]
 for i in range(55,len(rows)):
  w=rows[:i+1]
  s=tf_signal(w)
  if s.get("signal") in ("BUY","SELL"):
   markers.append({"time":rows[i].get("time"),"side":s["signal"],"price":float(rows[i]["low"] if s["signal"]=="BUY" else rows[i]["high"]),"confidence":s.get("confidence",0),"score":s.get("score",0)})
 return markers[-40:]
def refresh_perpetuals():
 rows=perpetuals(); ticks=perp_tickers()
 merged=[]
 for x in rows:
  y=dict(x); t=ticks.get(x.get("symbol"),{}); y.update({"close":t.get("close"),"mark_price":t.get("mark_price"),"index_price":t.get("spot_index_price"),"funding_rate":t.get("funding_rate"),"oi":t.get("open_interest"),"volume":t.get("volume"),"change_24h":t.get("ltp_change_24h")}); merged.append(y)
 with LOCK:CACHE["perpetuals"]=merged;CACHE["perp_ts"]=time.time()
def refresh():
 started=time.time(); out={};charts={};errors={}
 def fetch(res):
  try:
   rows=candles(res);return res,tf_signal(rows),{"candles":rows[-120:],"markers":chart_markers(rows),"patterns":candle_patterns(rows)},None
  except Exception as e:
   return res,{"signal":"HOLD","confidence":0,"reason":"feed unavailable","error":type(e).__name__+":"+str(e)[:120]},{"candles":[],"markers":[],"patterns":[]},type(e).__name__+":"+str(e)[:120]
 with ThreadPoolExecutor(max_workers=3) as pool:
  for res,sig,rows,err in pool.map(fetch,("1m","5m","1h")):
   out[res]=sig;charts[res]=rows
   if err: errors[res]=err
 out["_charts"]=charts;out["_meta"]={"updated_at":time.time(),"errors":errors,"latency_ms":round((time.time()-started)*1000)}
 try: out["_forecast"]=forecast(rd("data/live_microstructure_state.json"))
 except Exception as e: out["_forecast"]={"horizon_30s":{"direction":"UNRELIABLE","strength":0},"horizon_60s":{"direction":"UNRELIABLE","strength":0},"vetoes":["FORECAST_ERROR:"+type(e).__name__],"calibration":"UNVALIDATED","paper_only":True,"order_submission":False}
 with LOCK:
  CACHE["data"]=out;CACHE["errors"]=errors;CACHE["ts"]=time.time();CACHE["refresh_ms"]=out["_meta"]["latency_ms"]
 try:
  now=time.time(); state=rd("data/live_microstructure_state.json")
  if now-CACHE.get("forecast_record_ts",0)>=30 and out.get("_forecast"):
   record(state,out["_forecast"],30); CACHE["forecast_record_ts"]=now
  settle_once(state)
 except Exception as e:
  with LOCK:CACHE["errors"]["forecast_tracker"]=type(e).__name__+":"+str(e)[:120]
 refresh_perpetuals()
def refresher():
 while True:
  try:refresh()
  except Exception as e:
   with LOCK:CACHE["errors"]["global"]=type(e).__name__+":"+str(e)[:120]
  time.sleep(5)
def latest_cross():
 try:
  with open(ROOT+"/data/processed/cross_venue_btc_v43.jsonl") as f:
   ls=f.readlines()
   return json.loads(ls[-1]) if ls else {}
 except:return {}
class H(http.server.BaseHTTPRequestHandler):
 def send_json(self,obj):
  b=json.dumps(obj,separators=(",",":")).encode();self.send_response(200);self.send_header("Content-Type","application/json");self.send_header("Cache-Control","no-store");self.end_headers();self.wfile.write(b)
 def do_GET(self):
  path=urllib.parse.urlparse(self.path).path
  if path=="/":
   with open(ROOT+"/web/market_dashboard.html","rb") as f:b=f.read()
   self.send_response(200);self.send_header("Content-Type","text/html");self.end_headers();self.wfile.write(b);return
  if path=="/api/state":
   with LOCK:tf=json.loads(json.dumps(CACHE["data"]));meta={"cache_age_s":round(time.time()-CACHE["ts"],2) if CACHE["ts"] else None,"refresh_ms":CACHE["refresh_ms"],"errors":CACHE["errors"]}
   micro=rd("data/live_microstructure_state.json"); now=time.time(); q=micro.get("quality",{}); updated=float(micro.get("updated_at_epoch",0) or 0); file_age=(now-(os.path.getmtime(ROOT+"/data/live_microstructure_state.json") if os.path.exists(ROOT+"/data/live_microstructure_state.json") else 0)); event_fresh=float(q.get("fresh_seconds",999) if q.get("fresh_seconds") is not None else 999); state_age=max(0.0,now-updated) if updated else file_age; stale=state_age>6.0 or file_age>6.0 or event_fresh>6.0
   meta.update({"micro_event_fresh_s":round(event_fresh,3),"micro_state_age_s":round(state_age,3),"micro_file_age_s":round(file_age,3),"micro_stale":stale})
   self.send_json({"micro":micro,"cross":latest_cross(),"paper":rd("data/processed/professional_paper_v1_summary.json"),"timeframes":tf,"health":meta});return
  if path=="/api/patterns":
   with LOCK: tf=json.loads(json.dumps(CACHE["data"].get("_charts",{})))
   self.send_json({"timeframes":{k:{"patterns":v.get("patterns",[]),"markers":v.get("markers",[])} for k,v in tf.items()},"updated_at":time.time(),"paper_only":True});return
  if path=="/api/perpetuals":
   with LOCK:rows=json.loads(json.dumps(CACHE["perpetuals"]));age=round(time.time()-CACHE["perp_ts"],2) if CACHE["perp_ts"] else None
   self.send_json({"products":rows,"count":len([x for x in rows if x.get("symbol")]),"cache_age_s":age});return
  if path=="/api/absorption":
   summary=rd("data/processed/institutional_absorption_monitor_v2_state.json")
   latest={}
   try:
    with open(ROOT+"/data/processed/institutional_absorption_monitor_v2.jsonl") as f:
     ls=f.readlines(); latest=json.loads(ls[-1]) if ls else {}
   except: pass
   analytics=rd("data/processed/institutional_absorption_validation_v2.json")
   self.send_json({"summary":summary,"latest":latest,"analytics":analytics,"paper_only":True,"real_orders":False});return
  if path=="/api/advanced":
   with LOCK: data=json.loads(json.dumps(CACHE["data"])); perps=json.loads(json.dumps(CACHE["perpetuals"]))
   f=data.get("_forecast",{}); rows=[x for x in perps if x.get("symbol")]
   ranked=[]
   for x in rows:
    try:
     ch=abs(float(x.get("change_24h") or 0)); vol=abs(float(x.get("volume") or 0)); oi=abs(float(x.get("oi") or 0)); spread_hint=abs(float(x.get("taker_fee") or 0))*10000
     quality=max(0,min(100,50+min(ch*20,20)+min((vol/(oi+1))*100,15)-spread_hint))
    except: quality=0
    y=dict(x);y["market_quality"]=round(quality,1);ranked.append(y)
   ranked.sort(key=lambda z:z.get("market_quality",0),reverse=True)
   self.send_json({"forecast":f,"forecast_stats":forecast_stats(),"market_quality":ranked[:24],"paper_only":True,"order_submission":False});return
  if path=="/api/health":
   with LOCK:age=time.time()-CACHE["ts"] if CACHE["ts"] else 999;errs=dict(CACHE["errors"])
   micro=rd("data/live_microstructure_state.json");q=micro.get("quality",{})
   now=time.time();updated=float(micro.get("updated_at_epoch",0) or 0);file_age=(now-(os.path.getmtime(ROOT+"/data/live_microstructure_state.json") if os.path.exists(ROOT+"/data/live_microstructure_state.json") else 0))
   event_fresh=float(q.get("fresh_seconds",999) if q.get("fresh_seconds") is not None else 999)
   state_age=max(0.0,now-updated) if updated else file_age
   stale=state_age>6.0 or file_age>6.0 or event_fresh>6.0
   self.send_json({"status":"OK" if age<45 and not stale else "DEGRADED","cache_age_s":round(age,2),"micro_fresh_s":round(event_fresh,3),"micro_state_age_s":round(state_age,3),"micro_file_age_s":round(file_age,3),"micro_stale":stale,"errors":errs,"server_time":now});return
  self.send_error(404)
 def log_message(self,*a):pass
if __name__=="__main__":
 refresh();refresh_perpetuals();threading.Thread(target=refresher,daemon=True).start()
 http.server.ThreadingHTTPServer(("127.0.0.1",PORT),H).serve_forever()
