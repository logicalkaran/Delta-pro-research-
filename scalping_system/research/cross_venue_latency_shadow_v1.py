"""Two-venue public WebSocket arrival/lead-lag shadow probe.

Connects to Binance BTCUSDT partial depth and Delta India BTCUSD L1.
No API keys, private endpoints, order submission, leverage or account access.
Arrival-lag measurements are local-observation diagnostics, not exchange clock
synchronization or guaranteed executable arbitrage latency.
"""
from __future__ import annotations
import json, math, statistics, threading, time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
import websocket
from strategy.cross_venue_v41 import VenueSnapshot
from strategy.cross_venue_edge_v42 import classify
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/processed/cross_venue_latency_shadow_v1.json'
LOG=ROOT/'data/processed/cross_venue_latency_shadow_v1.jsonl'
DURATION_SECONDS=30
MAX_ROWS=30000
DELTA_URL='wss://public-socket.india.delta.exchange'
BINANCE_URL='wss://stream.binance.com:9443/ws/btcusdt@depth5@100ms'
STOP=threading.Event(); LOCK=threading.Lock(); EVENTS=deque(maxlen=MAX_ROWS); STATUS={}

def n(x):
 try:
  v=float(x); return v if math.isfinite(v) else None
 except (TypeError,ValueError): return None

def iso_now():return datetime.now(timezone.utc).isoformat()
def parse_binance_quote(d):
 bids=d.get('bids') or d.get('b') or []
 asks=d.get('asks') or d.get('a') or []
 if not bids or not asks:return None
 event_ms=n(d.get('E')); event_ts=event_ms/1000 if event_ms else None
 return event_ts,n(bids[0][0]),n(asks[0][0])

def add(venue,recv,event_ts,bid,ask,raw_type):
 if bid is None or ask is None or bid<=0 or ask<bid:return
 row={'venue':venue,'receive_epoch':recv,'receive_utc':iso_now(),'exchange_event_ts':event_ts,'bid':bid,'ask':ask,'mid':(bid+ask)/2,'spread_bps':(ask-bid)/((ask+bid)/2)*10000,'type':raw_type}
 with LOCK: EVENTS.append(row)

def delta_worker():
 while not STOP.is_set():
  ws=None
  try:
   ws=websocket.create_connection(DELTA_URL,timeout=5,enable_multithread=True)
   ws.settimeout(2)
   ws.send(json.dumps({'type':'subscribe','payload':{'channels':[{'name':'ob_l1','symbols':['BTCUSD']}]}}))
   with LOCK: STATUS['delta']={'connected':True,'connected_at':iso_now(),'errors':0}
   while not STOP.is_set():
    try: raw=ws.recv()
    except websocket.WebSocketTimeoutException: continue
    recv=time.time()
    try:
     d=json.loads(raw)
     if d.get('type')!='ob_l1':continue
     bid=n(d.get('bp'));ask=n(d.get('ap'))
     ts=n(d.get('ts'))
     if ts and ts>1e14:ts/=1e6
     elif ts and ts>1e11:ts/=1e3
     add('delta_india',recv,ts,bid,ask,'ob_l1')
    except Exception:
     with LOCK: STATUS.setdefault('delta',{}).setdefault('parse_errors',0);STATUS['delta']['parse_errors']+=1
  except Exception as e:
   with LOCK:
    s=STATUS.setdefault('delta',{'errors':0});s['errors']=s.get('errors',0)+1;s['last_error_type']=type(e).__name__
   time.sleep(1)
  finally:
   try:ws.close()
   except Exception:pass

def binance_worker():
 while not STOP.is_set():
  ws=None
  try:
   ws=websocket.create_connection(BINANCE_URL,timeout=5,enable_multithread=True)
   ws.settimeout(2)
   with LOCK: STATUS['binance']={'connected':True,'connected_at':iso_now(),'errors':0}
   while not STOP.is_set():
    try: raw=ws.recv()
    except websocket.WebSocketTimeoutException: continue
    recv=time.time()
    try:
     d=json.loads(raw);quote=parse_binance_quote(d)
     if quote is None:continue
     event_ts,bid,ask=quote
     add('binance',recv,event_ts,bid,ask,'depth5@100ms')
    except Exception:
     with LOCK: STATUS.setdefault('binance',{}).setdefault('parse_errors',0);STATUS['binance']['parse_errors']+=1
  except Exception as e:
   with LOCK:
    s=STATUS.setdefault('binance',{'errors':0});s['errors']=s.get('errors',0)+1;s['last_error_type']=type(e).__name__
   time.sleep(1)
  finally:
   try:ws.close()
   except Exception:pass

def pct(vals,p):
 if not vals:return None
 a=sorted(vals); x=(len(a)-1)*p/100;i=int(x);j=min(i+1,len(a)-1)
 return a[i]+(a[j]-a[i])*(x-i)
def summarize():
 with LOCK: rows=list(EVENTS); status=json.loads(json.dumps(STATUS))
 latest_by_venue={}
 for row in rows: latest_by_venue[row['venue']]=row
 v42=None
 if 'binance' in latest_by_venue and 'delta_india' in latest_by_venue:
  a=latest_by_venue['binance'];b=latest_by_venue['delta_india']
  v42=classify([VenueSnapshot('binance_BTCUSDT',a['mid'],a['bid'],a['ask']),VenueSnapshot('delta_india_BTCUSD',b['mid'],b['bid'],b['ask'])])
 result={'schema':'cross_venue_latency_shadow_v1','generated_at':iso_now(),'duration_seconds':DURATION_SECONDS,'mode':'PUBLIC_WEBSOCKET_DRY_RUN','real_orders':False,'private_api':False,'exchange_mutations':False,'credentials_used':False,'venue_status':status,'event_counts':{},'latest_quotes':{k:{key:v.get(key) for key in ('receive_epoch','receive_utc','bid','ask','mid','spread_bps','exchange_event_ts')} for k,v in latest_by_venue.items()},'cross_venue_edge_v42_dry_run':v42,'classifier_semantics':'V4.2 compares contemporaneous relative premiums around the mean reference price; it does not infer temporal leader/lagger propagation and does not authorize an order.','event_counts':{},'clock_quality':{},'arrival_lag':{},'lead_lag_diagnostics':{},'limitations':[]}
 for venue in ('binance','delta_india'):
  rr=[r for r in rows if r['venue']==venue]; result['event_counts'][venue]=len(rr)
  gaps=[(b['receive_epoch']-a['receive_epoch'])*1000 for a,b in zip(rr,rr[1:])]
  ex=[]
  for r in rr:
   if r['exchange_event_ts'] is not None:ex.append((r['receive_epoch']-r['exchange_event_ts'])*1000)
  result['clock_quality'][venue]={'event_timestamp_samples':len(ex),'negative_receive_minus_exchange_samples':sum(x<0 for x in ex),'receive_minus_exchange_ms_p50':pct([x for x in ex if x>=0],50),'receive_minus_exchange_ms_p95':pct([x for x in ex if x>=0],95),'clock_offset_unknown':True,'event_timestamp_semantics_verified':False,'inter_venue_one_way_latency_proven':False,'receive_gap_ms_p50':pct(gaps,50),'receive_gap_ms_p95':pct(gaps,95),'receive_gap_ms_max':max(gaps) if gaps else None}
 # Compare nearest local receive observations; this is arrival-time divergence, not a clean lead-lag estimate.
 b=[r for r in rows if r['venue']=='binance'];d=[r for r in rows if r['venue']=='delta_india']
 b.sort(key=lambda r:r['receive_epoch']);d.sort(key=lambda r:r['receive_epoch'])
 pairs=[]; j=0
 for x in b:
  while j+1<len(d) and abs(d[j+1]['receive_epoch']-x['receive_epoch'])<=abs(d[j]['receive_epoch']-x['receive_epoch']):j+=1
  if d and abs(d[j]['receive_epoch']-x['receive_epoch'])<=0.25:
   pairs.append((x,d[j],(d[j]['receive_epoch']-x['receive_epoch'])*1000))
 lags=[p[2] for p in pairs]
 result['arrival_lag']={'nearest_pairs_within_250ms':len(pairs),'delta_receive_minus_binance_receive_ms_p50':pct(lags,50),'p10':pct(lags,10),'p90':pct(lags,90),'positive_means_delta_observed_later':True,'not_network_one_way_latency':True}
 # Tiny descriptive price movement correlation on nearest paired arrivals only; no prediction or orders.
 moves=[]
 for (x,dx,_),(y,dy,_) in zip(pairs,pairs[1:]):
  if x['mid']>0 and dx['mid']>0 and y['mid']>0 and dy['mid']>0:
   moves.append({'binance_bps':(y['mid']/x['mid']-1)*10000,'delta_bps':(dy['mid']/dx['mid']-1)*10000,'dt_ms':(y['receive_epoch']-x['receive_epoch'])*1000})
 if len(moves)>=3:
  bm=[z['binance_bps'] for z in moves];dm=[z['delta_bps'] for z in moves]
  mb=statistics.fmean(bm);md=statistics.fmean(dm);den=math.sqrt(sum((v-mb)**2 for v in bm)*sum((v-md)**2 for v in dm))
  corr=sum((u-mb)*(v-md) for u,v in zip(bm,dm))/den if den else None
 else:corr=None
 result['lead_lag_diagnostics']={'paired_return_samples':len(moves),'contemporaneous_return_correlation':corr,'predictive_lead_lag_test':'NOT_ESTABLISHED','cross_venue_symbols_not_identical':True,'contract_basis_not_adjusted':True}
 result['limitations']=['No private order acknowledgement or execution latency measured','Binance BTCUSDT spot-like book and Delta BTCUSD perpetual are different instruments; basis and contract mechanics are not normalized','Exchange timestamps and local clock synchronization are unverified','Nearest arrival pairing is descriptive and cannot prove Binance leads Delta','Short probe is not enough for predictive validation','No live execution, order API, credentials, leverage or account endpoint used']
 return result

def main():
 start=time.time();threads=[threading.Thread(target=delta_worker,daemon=True),threading.Thread(target=binance_worker,daemon=True)]
 for t in threads:t.start()
 try:
  while time.time()-start<DURATION_SECONDS:time.sleep(.25)
 finally:STOP.set()
 for t in threads:t.join(timeout=3)
 report=summarize();report['elapsed_seconds']=round(time.time()-start,2)
 OUT.parent.mkdir(parents=True,exist_ok=True);tmp=OUT.with_suffix('.tmp');tmp.write_text(json.dumps(report,indent=2,allow_nan=False));tmp.replace(OUT)
 with LOG.open('a',encoding='utf-8') as f:f.write(json.dumps(report,separators=(',',':'),allow_nan=False)+'\n')
 print(json.dumps({k:report[k] for k in ('mode','elapsed_seconds','venue_status','event_counts','clock_quality','arrival_lag','lead_lag_diagnostics','real_orders','limitations')},indent=2),flush=True)
if __name__=='__main__':main()
