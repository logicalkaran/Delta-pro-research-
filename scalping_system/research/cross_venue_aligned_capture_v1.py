"""Research-only Binance USD-M perpetual / Delta India perpetual capture.

Captures Binance aggTrade + sequence-checked diff depth and Delta trades/L1/L2.
Uses bounded in-memory buffers, append-only JSONL, no pandas, no credentials,
no private endpoints and no execution. A sweep is only a research candidate.
"""
from __future__ import annotations
import argparse, json, math, statistics, threading, time, urllib.request
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
import websocket

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'data/raw/cross_venue_aligned'
BINANCE_WS='wss://fstream.binance.com/stream?streams=btcusdt@aggTrade/btcusdt@depth@100ms'
BINANCE_DEPTH='https://fapi.binance.com/fapi/v1/depth?symbol=BTCUSDT&limit=1000'
BINANCE_INFO='https://fapi.binance.com/fapi/v1/exchangeInfo'
DELTA_WS='wss://public-socket.india.delta.exchange'
SYMBOL='BTCUSD'
BUFFER_MAX=2000
FLOW_WINDOW_S=.5
SWEEP_LEVELS=3
FLOW_QUANTILE=.99
FLOW_MIN_SAMPLES=600
FLOW_BASELINE_MAX=18000
STOP=threading.Event(); LOCK=threading.RLock()
QUOTES={'binance':None,'delta':None}
QUOTE_HISTORY={'binance':deque(maxlen=BUFFER_MAX),'delta':deque(maxlen=BUFFER_MAX)}
FLOW=deque()  # (monotonic, signed BTC quantity)
FLOW_BASELINE=deque(maxlen=FLOW_BASELINE_MAX)
LAST_FLOW_SAMPLE=0.0; LAST_THRESHOLD_REFRESH=0.0; LAST_FLOW_THRESHOLD=None
PENDING=[]
COUNTS={'binance_aggTrade':0,'binance_depthUpdate':0,'delta_trades':0,'delta_ob_l1':0,'delta_ob_l2':0,'bad_rows':0,'sequence_gaps':0,'stale_drops':0,'sweep_candidates':0,'labeled_sweeps':0}
STATUS={'binance':'starting','delta':'starting'}
OUT_RAW=None; OUT_SWEEPS=None; OUT_LABELS=None; RAW_F=None; SWEEP_F=None; LABEL_F=None
TICK_SIZE=.1

def now_iso(): return datetime.now(timezone.utc).isoformat()
def num(x):
 try:
  y=float(x); return y if math.isfinite(y) else None
 except (TypeError,ValueError): return None
def ts_seconds(x):
 v=num(x)
 if v is None:return None
 if v>1e14:return v/1e6
 if v>1e11:return v/1e3
 return v
def write_row(f,row):
 f.write(json.dumps(row,separators=(',',':'),allow_nan=False)+'\n')
def emit_raw(row):
 global RAW_F
 with LOCK: write_row(RAW_F,row)
def quote(venue,bid,ask,engine_ts,recv_wall,recv_mono,source):
 if bid is None or ask is None or bid<=0 or ask<bid:return None
 row={'venue':venue,'source':source,'engine_ts_s':ts_seconds(engine_ts),'receive_epoch_s':recv_wall,'receive_utc':now_iso(),'receive_mono_s':recv_mono,'bid':bid,'ask':ask,'mid':(bid+ask)/2,'spread_bps':(ask-bid)/((ask+bid)/2)*10000}
 with LOCK:
  QUOTES[venue]=row;QUOTE_HISTORY[venue].append(row)
 return row

def nearest_quantile(values,q):
 if not values:return None
 a=sorted(values);return a[min(len(a)-1,max(0,math.ceil(q*len(a))-1))]

def signed_flow(now_mono):
 while FLOW and now_mono-FLOW[0][0]>.5:FLOW.popleft()
 return sum(x[1] for x in FLOW)

def maybe_sweep(now_mono,recv_wall,engine_ts,old_bid,old_ask,new_bid,new_ask):
 global LAST_FLOW_SAMPLE,LAST_THRESHOLD_REFRESH,LAST_FLOW_THRESHOLD
 # Sample 500ms signed trade flow at most every 100ms, for an adaptive threshold.
 if now_mono-LAST_FLOW_SAMPLE>=.1:
  v=signed_flow(now_mono);FLOW_BASELINE.append(abs(v));LAST_FLOW_SAMPLE=now_mono
  if len(FLOW_BASELINE)>=FLOW_MIN_SAMPLES and now_mono-LAST_THRESHOLD_REFRESH>=1.0:
   LAST_FLOW_THRESHOLD=nearest_quantile(list(FLOW_BASELINE),FLOW_QUANTILE);LAST_THRESHOLD_REFRESH=now_mono
 signed=signed_flow(now_mono)
 if old_bid is None or old_ask is None or new_bid is None or new_ask is None:return
 # Ask lifting implies buy sweep; bid dropping implies sell sweep.
 up=max(0,int(round((new_ask-old_ask)/TICK_SIZE)))
 down=max(0,int(round((old_bid-new_bid)/TICK_SIZE)))
 direction=1 if up>=SWEEP_LEVELS and signed>0 else -1 if down>=SWEEP_LEVELS and signed<0 else 0
 if not direction:return
 if LAST_FLOW_THRESHOLD is None or abs(signed)<LAST_FLOW_THRESHOLD:return
 event={'schema':'cross_venue_sweep_candidate_v1','candidate_id':f'{int(recv_wall*1e6)}-{COUNTS["sweep_candidates"]+1}','direction':direction,'direction_text':'BUY' if direction>0 else 'SELL','engine_ts_s':ts_seconds(engine_ts),'receive_epoch_s':recv_wall,'receive_utc':now_iso(),'receive_mono_s':now_mono,'signed_flow_500ms':signed,'rolling_abs_flow_p99':LAST_FLOW_THRESHOLD,'cleared_price_levels_estimate':up if direction>0 else down,'tick_size':TICK_SIZE,'binance_best_bid':new_bid,'binance_best_ask':new_ask,'research_only':True,'real_orders':False,'definition':'500ms signed aggTrade volume exceeds rolling 99th percentile and best ask rises / best bid falls by at least 3 ticks; candidate only, not proof of a sweep or executable fill'}
 with LOCK:
  COUNTS['sweep_candidates']+=1;write_row(SWEEP_F,event);PENDING.append({'event':event,'due_mono':now_mono+1.0,'base':None,'targets':{5:None,15:None,30:None}})

def update_pending(now_mono):
 global PENDING
 with LOCK:
  remain=[]
  for p in PENDING:
   if p['base'] is None and now_mono>=p['due_mono']:
    # The 1-second buffer makes this an actionable receive-time test, not engine-time causality.
    q={v:QUOTES[v] for v in ('binance','delta')}
    if any(x is None or now_mono-x['receive_mono_s']>1.0 for x in q.values()):
     p['event']['label_status']='BASELINE_MISSING_OR_STALE';p['base']='invalid'
    else:p['base']={v:dict(q[v]) for v in q}
   if isinstance(p['base'],dict):
    age=now_mono-p['due_mono']
    for h in (5,15,30):
     if p['targets'][h] is None and age>=h:
      q={v:QUOTES[v] for v in ('binance','delta')}
      if all(x is not None and now_mono-x['receive_mono_s']<=1.0 for x in q.values()):p['targets'][h]={v:dict(q[v]) for v in q}
   done=p['base']=='invalid' or (isinstance(p['base'],dict) and all(p['targets'][h] is not None for h in (5,15,30)))
   if done:
    ev=p['event'];out={'schema':'cross_venue_sweep_label_v1','candidate_id':ev['candidate_id'],'direction':ev['direction'],'sweep_receive_epoch_s':ev['receive_epoch_s'],'buffer_seconds':1,'outcomes':{},'timestamp_basis':'local monotonic receive time after 1s buffer; exchange engine timestamps preserved separately but not treated as synchronized','research_only':True,'real_orders':False}
    if p['base']=='invalid':out['status']='BASELINE_MISSING_OR_STALE'
    else:
     out['status']='OK'
     for h in (5,15,30):
      base=p['base'];target=p['targets'][h];ret={}
      for v in ('binance','delta'):
       a=base[v]['mid'];b=target[v]['mid'];ret[v+'_log_return_bps']=10000*math.log(b/a) if a>0 and b>0 else None
      if ret['binance_log_return_bps'] is not None and ret['delta_log_return_bps'] is not None:
       ret['return_differential_binance_minus_delta_bps']=ret['binance_log_return_bps']-ret['delta_log_return_bps']
       ret['delta_directional_followthrough_bps']=ev['direction']*ret['delta_log_return_bps']
      ret['delta_spread_bps_at_target']=target['delta']['spread_bps'];ret['binance_spread_bps_at_target']=target['binance']['spread_bps'];out['outcomes'][str(h)+'s']=ret
    write_row(LABEL_F,out);COUNTS['labeled_sweeps']+=1
   else:remain.append(p)
  PENDING=remain

def binance_worker():
 global TICK_SIZE
 while not STOP.is_set():
  ws=None
  try:
   # Fetch public exchange metadata for the exact tick size.
   with urllib.request.urlopen(BINANCE_INFO,timeout=8) as r:info=json.loads(r.read().decode())
   for s in info.get('symbols',[]):
    if s.get('symbol')=='BTCUSDT':
     for flt in s.get('filters',[]):
      if flt.get('filterType')=='PRICE_FILTER':TICK_SIZE=float(flt['tickSize'])
   with urllib.request.urlopen(BINANCE_DEPTH,timeout=8) as r:snap=json.loads(r.read().decode())
   bids={float(p):float(q) for p,q in snap['bids']};asks={float(p):float(q) for p,q in snap['asks']};last_id=int(snap['lastUpdateId']);synced=False
   ws=websocket.create_connection(BINANCE_WS,timeout=8,enable_multithread=True);ws.settimeout(2)
   with LOCK:STATUS['binance']='connected_waiting_for_depth_sync'
   while not STOP.is_set():
    try:raw=ws.recv()
    except websocket.WebSocketTimeoutException:continue
    recv_wall=time.time();recv_mono=time.monotonic()
    try:
     wrapper=json.loads(raw);d=wrapper.get('data',wrapper);stream=wrapper.get('stream','');kind=d.get('e')
     if kind=='aggTrade':
      price=num(d.get('p'));qty=num(d.get('q'));maker=d.get('m');side=-1 if maker else 1
      if price is None or qty is None:continue
      with LOCK:FLOW.append((recv_mono,side*qty));COUNTS['binance_aggTrade']+=1
      row={'venue':'binance','kind':'aggTrade','symbol':'BTCUSDT','engine_event_ts_s':ts_seconds(d.get('E')),'engine_transaction_ts_s':ts_seconds(d.get('T')),'receive_epoch_s':recv_wall,'receive_utc':now_iso(),'receive_mono_s':recv_mono,'trade_id':d.get('a'),'price':price,'quantity_btc':qty,'aggressor_side':'SELL' if maker else 'BUY','buyer_is_maker':maker,'book_synced':synced}
      emit_raw(row);continue
     if kind!='depthUpdate':continue
     U=int(d['U']);u=int(d['u'])
     if u<=last_id:continue
     if not synced:
      if not (U<=last_id+1<=u):
       # Snapshot-to-stream sequence gap: resync instead of using a broken book.
       with LOCK:COUNTS['sequence_gaps']+=1;STATUS['binance']='depth_sequence_gap_resnapshot'
       ws.close();ws=None;break
      synced=True
     elif U>last_id+1:
      with LOCK:COUNTS['sequence_gaps']+=1;STATUS['binance']='depth_sequence_gap_resnapshot'
      ws.close();ws=None;break
     old_bid=max(bids) if bids else None;old_ask=min(asks) if asks else None
     for p,q in d.get('b',[]):
      p=float(p);q=float(q)
      if q==0:bids.pop(p,None)
      else:bids[p]=q
     for p,q in d.get('a',[]):
      p=float(p);q=float(q)
      if q==0:asks.pop(p,None)
      else:asks[p]=q
     last_id=u;best_bid=max(bids) if bids else None;best_ask=min(asks) if asks else None
     if best_bid is None or best_ask is None:continue
     q=quote('binance',best_bid,best_ask,d.get('T') or d.get('E'),recv_wall,recv_mono,'depthUpdate')
     if q is None:continue
     with LOCK:COUNTS['binance_depthUpdate']+=1;STATUS['binance']='connected_synced'
     row={'venue':'binance','kind':'depthUpdate','symbol':'BTCUSDT','engine_event_ts_s':ts_seconds(d.get('E')),'engine_transaction_ts_s':ts_seconds(d.get('T')),'receive_epoch_s':recv_wall,'receive_utc':q['receive_utc'],'receive_mono_s':recv_mono,'first_update_id':U,'final_update_id':u,'best_bid':best_bid,'best_ask':best_ask,'mid':q['mid'],'spread_bps':q['spread_bps'],'bid_depth_top10_btc':sum(bids[p] for p in sorted(bids,reverse=True)[:10]),'ask_depth_top10_btc':sum(asks[p] for p in sorted(asks)[:10]),'book_synced':True,'tick_size':TICK_SIZE}
     emit_raw(row);maybe_sweep(recv_mono,recv_wall,d.get('T') or d.get('E'),old_bid,old_ask,best_bid,best_ask);update_pending(recv_mono)
    except Exception:
     with LOCK:COUNTS['bad_rows']+=1
  except Exception as e:
   with LOCK:STATUS['binance']='error:'+type(e).__name__
   time.sleep(1)
  finally:
   try:
    if ws:ws.close()
   except Exception:pass

def delta_worker():
 while not STOP.is_set():
  ws=None
  try:
   ws=websocket.create_connection(DELTA_WS,timeout=8,enable_multithread=True);ws.settimeout(2)
   ws.send(json.dumps({'type':'subscribe','payload':{'channels':[{'name':'trades','symbols':[SYMBOL]},{'name':'ob_l1','symbols':[SYMBOL]},{'name':'ob_l2','symbols':[SYMBOL]}]}}))
   with LOCK:STATUS['delta']='connected'
   while not STOP.is_set():
    try:raw=ws.recv()
    except websocket.WebSocketTimeoutException:continue
    recv_wall=time.time();recv_mono=time.monotonic()
    try:
     d=json.loads(raw);typ=d.get('type')
     if typ not in ('trades','ob_l1','ob_l2'):continue
     bid=ask=None;engine_ts=d.get('ts')
     if typ=='ob_l1':bid=num(d.get('bp'));ask=num(d.get('ap'))
     elif typ=='ob_l2':
      bids=d.get('b') or [];asks=d.get('a') or []
      if bids and asks:bid=num(bids[0][0]);ask=num(asks[0][0])
     elif typ=='trades':
      with LOCK:COUNTS['delta_trades']+=1
      row={'venue':'delta','kind':'trade','symbol':SYMBOL,'engine_trade_ts_s':ts_seconds(d.get('t')),'feed_ts_s':ts_seconds(d.get('ts')),'receive_epoch_s':recv_wall,'receive_utc':now_iso(),'receive_mono_s':recv_mono,'price':num(d.get('p')),'quantity_contract_units':num(d.get('s')),'role':d.get('r'),'raw_side_semantics':'preserved_as_exchange_role_field_not_assumed','research_only':True}
      emit_raw(row);continue
     q=quote('delta',bid,ask,engine_ts,recv_wall,recv_mono,typ)
     if q is None:continue
     if typ=='ob_l1':
      with LOCK:COUNTS['delta_ob_l1']+=1
      row={'venue':'delta','kind':'ob_l1','symbol':SYMBOL,'engine_ts_s':q['engine_ts_s'],'receive_epoch_s':recv_wall,'receive_utc':q['receive_utc'],'receive_mono_s':recv_mono,'best_bid':bid,'best_ask':ask,'mid':q['mid'],'spread_bps':q['spread_bps'],'bid_size':num(d.get('bs')),'ask_size':num(d.get('as'))}
     else:
      with LOCK:COUNTS['delta_ob_l2']+=1
      row={'venue':'delta','kind':'ob_l2_snapshot','symbol':SYMBOL,'engine_ts_s':q['engine_ts_s'],'receive_epoch_s':recv_wall,'receive_utc':q['receive_utc'],'receive_mono_s':recv_mono,'best_bid':bid,'best_ask':ask,'mid':q['mid'],'spread_bps':q['spread_bps'],'bid_levels':(d.get('b') or [])[:20],'ask_levels':(d.get('a') or [])[:20]}
     emit_raw(row);update_pending(recv_mono)
    except Exception:
     with LOCK:COUNTS['bad_rows']+=1
  except Exception as e:
   with LOCK:STATUS['delta']='error:'+type(e).__name__;time.sleep(1)
  finally:
   try:
    if ws:ws.close()
   except Exception:pass

def main():
 global OUT_RAW,OUT_SWEEPS,OUT_LABELS,RAW_F,SWEEP_F,LABEL_F
 ap=argparse.ArgumentParser();ap.add_argument('--duration-seconds',type=int,default=600);args=ap.parse_args()
 BASE.mkdir(parents=True,exist_ok=True);stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
 OUT_RAW=BASE/f'cross_venue_ticks_{stamp}.jsonl';OUT_SWEEPS=BASE/f'cross_venue_sweeps_{stamp}.jsonl';OUT_LABELS=BASE/f'cross_venue_labels_{stamp}.jsonl'
 with OUT_RAW.open('a',encoding='utf-8',buffering=1) as RAW_F, OUT_SWEEPS.open('a',encoding='utf-8',buffering=1) as SWEEP_F, OUT_LABELS.open('a',encoding='utf-8',buffering=1) as LABEL_F:
  threads=[threading.Thread(target=binance_worker,daemon=True),threading.Thread(target=delta_worker,daemon=True)]
  for t in threads:t.start()
  start=time.monotonic();last_flush=start
  try:
   while time.monotonic()-start<args.duration_seconds:
    now=time.monotonic();update_pending(now)
    if now-last_flush>=1:
     RAW_F.flush();SWEEP_F.flush();LABEL_F.flush();last_flush=now
    time.sleep(.05)
  except KeyboardInterrupt:pass
  finally:
   STOP.set()
   for t in threads:t.join(timeout=3)
   RAW_F.flush();SWEEP_F.flush();LABEL_F.flush()
 report={'schema':'cross_venue_aligned_capture_report_v1','started_at_utc':stamp,'finished_at_utc':now_iso(),'duration_requested_seconds':args.duration_seconds,'mode':'PUBLIC_RESEARCH_CAPTURE_ONLY','binance_symbol':'BTCUSDT USD-M perpetual','delta_symbol':SYMBOL+' Delta India perpetual','raw_path':str(OUT_RAW.relative_to(ROOT)),'sweeps_path':str(OUT_SWEEPS.relative_to(ROOT)),'labels_path':str(OUT_LABELS.relative_to(ROOT)),'counts':COUNTS,'status':STATUS,'tick_size':TICK_SIZE,'buffers':{'per_venue_quote_history_max':BUFFER_MAX,'trade_flow_window_seconds':FLOW_WINDOW_S,'flow_baseline_max_samples':FLOW_BASELINE_MAX},'sweep_rule':{'window_seconds':FLOW_WINDOW_S,'flow_quantile':FLOW_QUANTILE,'minimum_baseline_samples':FLOW_MIN_SAMPLES,'levels':SWEEP_LEVELS,'buffer_seconds':1,'horizons_seconds':[5,15,30]},'timestamp_policy':'Preserve engine event/transaction timestamps and local receive wall/monotonic times separately. Cross-venue engine clocks are not assumed synchronized. Outcomes are receive-time actionable labels after a 1s buffer.','real_orders':False,'private_api':False,'credentials_used':False,'execution_enabled':False,'qwen_enabled':False,'notes':['Binance book only becomes eligible after diff-depth sequence synchronization.','Sweep candidates are observational and not proof of passive fill or profitable transmission.','Delta trade size is preserved as exchange contract units, not assumed BTC.','Depth/top-of-book units and contract multiplier require explicit instrument-spec verification before economic interpretation.']}
 report_path=BASE/f'cross_venue_capture_report_{stamp}.json';report_path.write_text(json.dumps(report,indent=2,allow_nan=False));print(json.dumps(report,indent=2),flush=True)
if __name__=='__main__':main()
