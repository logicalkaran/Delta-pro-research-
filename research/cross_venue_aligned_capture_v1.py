"""Research-only Binance USD-M perpetual / Delta India perpetual capture.

Captures Binance aggTrade + sequence-checked diff depth and Delta trades/L1/L2.
Uses bounded in-memory buffers, append-only JSONL, no pandas, no credentials,
no private endpoints and no execution. A sweep is only a research candidate.
"""
from __future__ import annotations
import argparse, asyncio, json, math, signal, statistics, threading, time, urllib.parse, urllib.request
from contextlib import ExitStack
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
import websocket

ROOT=Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT))
from delta_collector.partitioned_raw_writer import PartitionedGzipJSONLWriter
BASE=ROOT/'data/raw/cross_venue_aligned'
BINANCE_WS='wss://fstream.binance.com/public/ws/btcusdt@depth@100ms'
BINANCE_TRADE_WS='wss://fstream.binance.com/market/ws/btcusdt@aggTrade'
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
CAPTURE_ONLY=False
QUOTES={'binance':None,'delta':None}
QUOTE_HISTORY={'binance':deque(maxlen=BUFFER_MAX),'delta':deque(maxlen=BUFFER_MAX)}
FLOW=deque()  # (monotonic, signed BTC quantity, trade price)
FLOW_BASELINE=deque(maxlen=FLOW_BASELINE_MAX)
LAST_FLOW_SAMPLE=0.0; LAST_THRESHOLD_REFRESH=0.0; LAST_FLOW_THRESHOLD=None
PENDING=[]
COUNTS={'binance_aggTrade':0,'binance_depthUpdate':0,'delta_trades':0,'delta_ob_l1':0,'delta_ob_l2':0,'bad_rows':0,'sequence_gaps':0,'aggtrade_gaps_detected':0,'aggtrade_backfill_successes':0,'aggtrade_backfill_failures':0,'aggtrade_backfilled_rows':0,'stale_drops':0,'sweep_candidates':0,'labeled_sweeps':0}
STATUS={'binance':'starting','delta':'starting'}
OUT_RAW=None; OUT_SWEEPS=None; OUT_LABELS=None; RAW_F=None; RAW_WRITER=None; SWEEP_F=None; LABEL_F=None
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
 global RAW_WRITER
 with LOCK:
  if RAW_WRITER is None:
   raise RuntimeError('raw gzip partition writer is not initialized')
  RAW_WRITER.write(row)
def quote(venue,bid,ask,engine_ts,recv_wall,recv_mono,source):
 if bid is None or ask is None or bid<=0 or ask<bid:return None
 row={'venue':venue,'source':source,'engine_ts_s':ts_seconds(engine_ts),'receive_epoch_s':recv_wall,'receive_utc':now_iso(),'receive_mono_s':recv_mono,'bid':bid,'ask':ask,'mid':(bid+ask)/2,'spread_bps':(ask-bid)/((ask+bid)/2)*10000}
 with LOCK:
  QUOTES[venue]=row;QUOTE_HISTORY[venue].append(row)
 return row

def parse_binance_depth(payload: dict) -> dict:
 """Normalize Binance USD-M depth IDs; research ingestion only, no execution."""
 return {'exchange':'binance','first_update_id':payload.get('U'),
         'final_update_id':payload.get('u'),'previous_update_id':payload.get('pu'),
         'bids':payload.get('b',[]),'asks':payload.get('a',[])}


def _fetch_aggtrade_page(from_id: int) -> list:
 """Fetch one public USD-M aggregate-trade page; never uses credentials."""
 query=urllib.parse.urlencode({'symbol':'BTCUSDT','fromId':from_id,'limit':1000})
 request=urllib.request.Request('https://fapi.binance.com/fapi/v1/aggTrades?'+query,
                                headers={'User-Agent':'btc-fisher-research-capture/1.0'})
 with urllib.request.urlopen(request,timeout=5) as response:
  payload=json.loads(response.read().decode('utf-8'))
 if not isinstance(payload,list):
  raise ValueError('Unexpected Binance aggTrades response schema')
 return payload


async def backfill_aggtrade_gap(from_id: int, to_id: int) -> tuple[bool,int]:
 """Backfill a bounded ID interval, preserving canonical schema and source labels.

 Uses async offloading for REST I/O. The capture worker pauses consuming its socket
 while this runs; queued frames are deduplicated by aggregate trade ID afterward.
 No automatic retries; unresolved intervals are explicitly archived for audit.
 """
 cursor=from_id; written=0; pages=0
 while cursor<=to_id and pages<10:
  page=await asyncio.to_thread(_fetch_aggtrade_page,cursor); pages+=1
  if not page: break
  progressed=False
  for trade in page:
   try: tid=int(trade['a'])
   except (KeyError,TypeError,ValueError): continue
   if tid<cursor: continue
   if tid>cursor: return False,written
   price=num(trade.get('p')); qty=num(trade.get('q')); maker=trade.get('m')
   if price is None or qty is None or maker is None: return False,written
   recv_wall=time.time(); recv_mono=time.monotonic()
   emit_raw({'venue':'binance','kind':'aggTrade','symbol':'BTCUSDT',
    'engine_event_ts_s':None,'engine_transaction_ts_s':ts_seconds(trade.get('T')),
    'receive_epoch_s':recv_wall,'receive_utc':now_iso(),'receive_mono_s':recv_mono,
    'trade_id':tid,'price':price,'quantity_btc':qty,
    'aggressor_side':'SELL' if maker else 'BUY','buyer_is_maker':maker,
    'book_synced':STATUS.get('binance')=='connected_synced','is_backfilled':True,
    'backfill_source':'binance_futures_rest_aggTrades'})
   written+=1; cursor=tid+1; progressed=True
   if cursor>to_id: break
  if cursor>to_id: break
  if not progressed: break
 return cursor>to_id,written


class BinanceTradeHealer:
 """Research-only aggregate-trade sequence watcher; no trading or order access."""
 def __init__(self): self.expected_a=None

 def process_live_trade(self, payload: dict) -> None:
  current=payload.get('a')
  if not isinstance(current,int):
   try: current=int(current)
   except (TypeError,ValueError):
    with LOCK: COUNTS['bad_rows']+=1
    return
  if self.expected_a is not None and current<self.expected_a:
   # REST backfill or a reconnect may cause buffered duplicate stream frames.
   return
  if self.expected_a is not None and current>self.expected_a:
   start=self.expected_a; end=current-1
   with LOCK: COUNTS['aggtrade_gaps_detected']+=1
   try:
    complete,written=asyncio.run(backfill_aggtrade_gap(start,end))
   except Exception as exc:
    complete=False; written=0
    error=type(exc).__name__
   else: error=None
   with LOCK:
    COUNTS['aggtrade_backfilled_rows']+=written
    if complete: COUNTS['aggtrade_backfill_successes']+=1
    else:
     COUNTS['aggtrade_backfill_failures']+=1
     emit_raw({'venue':'binance','kind':'aggTrade_gap','symbol':'BTCUSDT',
      'gap_start_id':start,'gap_end_id':end,'detected_at_utc':now_iso(),
      'backfill_status':'INCOMPLETE','backfilled_rows':written,
      'error_type':error,'research_only':True,'real_orders':False})
  # The live frame follows the gap interval even if REST backfill fails; the marker preserves the unresolved gap.
  self.expected_a=current
  recv_wall=time.time(); recv_mono=time.monotonic()
  price=num(payload.get('p')); qty=num(payload.get('q')); maker=payload.get('m')
  if price is None or qty is None or maker is None:
   with LOCK: COUNTS['bad_rows']+=1
   self.expected_a=current+1
   return
  with LOCK:
   COUNTS['binance_aggTrade']+=1
   if not CAPTURE_ONLY: FLOW.append((recv_mono,(-1 if maker else 1)*qty,price))
  emit_raw({'venue':'binance','kind':'aggTrade','symbol':'BTCUSDT',
   'engine_event_ts_s':ts_seconds(payload.get('E')),'engine_transaction_ts_s':ts_seconds(payload.get('T')),
   'receive_epoch_s':recv_wall,'receive_utc':now_iso(),'receive_mono_s':recv_mono,
   'trade_id':current,'price':price,'quantity_btc':qty,
   'aggressor_side':'SELL' if maker else 'BUY','buyer_is_maker':maker,
   'book_synced':STATUS.get('binance')=='connected_synced','is_backfilled':False,
   'backfill_source':'websocket'})
  self.expected_a=current+1

def depth_snapshot_bridge(first_u,final_u,last_update_id):
 return int(first_u)<=int(last_update_id)<=int(final_u)

def depth_event_follows(previous_final_id,event_previous_id):
 return event_previous_id is not None and int(event_previous_id)==int(previous_final_id)

def nearest_quantile(values,q):
 if not values:return None
 a=sorted(values);return a[min(len(a)-1,max(0,math.ceil(q*len(a))-1))]

def signed_flow(now_mono):
 with LOCK:
  while FLOW and now_mono-FLOW[0][0]>.5:FLOW.popleft()
  return sum(x[1] for x in FLOW)

def count_swept_trade_levels(direction,old_best,new_best,now_mono):
 with LOCK: trades=[x for x in FLOW if now_mono-x[0]<=FLOW_WINDOW_S]
 if direction>0: prices=[x[2] for x in trades if x[1]>0 and old_best<=x[2]<new_best]
 else: prices=[x[2] for x in trades if x[1]<0 and new_best<x[2]<=old_best]
 return len({int(round(p/TICK_SIZE)) for p in prices})

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
 buy_levels=count_swept_trade_levels(1,old_ask,new_ask,now_mono) if up>=SWEEP_LEVELS and signed>0 else 0
 sell_levels=count_swept_trade_levels(-1,old_bid,new_bid,now_mono) if down>=SWEEP_LEVELS and signed<0 else 0
 direction=1 if up>=SWEEP_LEVELS and signed>0 and buy_levels>=SWEEP_LEVELS else -1 if down>=SWEEP_LEVELS and signed<0 and sell_levels>=SWEEP_LEVELS else 0
 if not direction:return
 if LAST_FLOW_THRESHOLD is None or abs(signed)<LAST_FLOW_THRESHOLD:return
 event={'schema':'cross_venue_sweep_candidate_v1','candidate_id':f'{int(recv_wall*1e6)}-{COUNTS["sweep_candidates"]+1}','direction':direction,'direction_text':'BUY' if direction>0 else 'SELL','engine_ts_s':ts_seconds(engine_ts),'receive_epoch_s':recv_wall,'receive_utc':now_iso(),'receive_mono_s':now_mono,'signed_flow_500ms':signed,'rolling_abs_flow_p99':LAST_FLOW_THRESHOLD,'best_price_ticks_moved':up if direction>0 else down,'executed_trade_price_levels_500ms':buy_levels if direction>0 else sell_levels,'tick_size':TICK_SIZE,'binance_best_bid':new_bid,'binance_best_ask':new_ask,'research_only':True,'real_orders':False,'definition':'500ms signed aggTrade volume exceeds rolling 99th percentile; best ask rises / best bid falls by at least 3 ticks; and at least 3 distinct aggressive-trade price levels were observed in the traversed interval. Still a candidate, not proof of no cancellations or executable fill'}
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
   # Start the stream before snapshot fetch so depth events buffer while REST snapshot loads.
   ws=websocket.create_connection(BINANCE_WS,timeout=8,enable_multithread=True);ws.settimeout(2)
   with LOCK:STATUS['binance']='connected_waiting_for_depth_sync'
   with urllib.request.urlopen(BINANCE_DEPTH,timeout=8) as r:snap=json.loads(r.read().decode())
   bids={float(p):float(q) for p,q in snap['bids']};asks={float(p):float(q) for p,q in snap['asks']};last_id=int(snap['lastUpdateId']);synced=False
   previous_u=None
   while not STOP.is_set():
    try:raw=ws.recv()
    except websocket.WebSocketTimeoutException:continue
    recv_wall=time.time();recv_mono=time.monotonic()
    try:
     wrapper=json.loads(raw);d=wrapper.get('data',wrapper);stream=wrapper.get('stream','');kind=d.get('e')
     if kind=='aggTrade':
      price=num(d.get('p'));qty=num(d.get('q'));maker=d.get('m');side=-1 if maker else 1
      if price is None or qty is None:continue
      with LOCK:
       COUNTS['binance_aggTrade']+=1
       if not CAPTURE_ONLY: FLOW.append((recv_mono,side*qty,price))
      row={'venue':'binance','kind':'aggTrade','symbol':'BTCUSDT','engine_event_ts_s':ts_seconds(d.get('E')),'engine_transaction_ts_s':ts_seconds(d.get('T')),'receive_epoch_s':recv_wall,'receive_utc':now_iso(),'receive_mono_s':recv_mono,'trade_id':d.get('a'),'price':price,'quantity_btc':qty,'aggressor_side':'SELL' if maker else 'BUY','buyer_is_maker':maker,'book_synced':synced}
      emit_raw(row);continue
     if kind!='depthUpdate':continue
     depth=parse_binance_depth(d); U=int(depth['first_update_id']);u=int(depth['final_update_id'])
     if u<=last_id:continue
     if not synced:
      if u<last_id:continue
      if not depth_snapshot_bridge(U,u,last_id):
       # Futures snapshot bridge failed: resync rather than calculate on a broken book.
       with LOCK:COUNTS['sequence_gaps']+=1;STATUS['binance']='depth_sequence_gap_resnapshot'
       ws.close();ws=None;break
      synced=True
     elif not depth_event_follows(previous_u,depth['previous_update_id']):
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
     last_id=u;previous_u=u;best_bid=max(bids) if bids else None;best_ask=min(asks) if asks else None
     if best_bid is None or best_ask is None:continue
     q=quote('binance',best_bid,best_ask,d.get('T') or d.get('E'),recv_wall,recv_mono,'depthUpdate')
     if q is None:continue
     with LOCK:COUNTS['binance_depthUpdate']+=1;STATUS['binance']='connected_synced'
     bid_prices=sorted(bids,reverse=True)[:5];ask_prices=sorted(asks)[:5]
     row={'venue':'binance','kind':'depthUpdate','symbol':'BTCUSDT','engine_event_ts_s':ts_seconds(d.get('E')),'engine_transaction_ts_s':ts_seconds(d.get('T')),'receive_epoch_s':recv_wall,'receive_utc':q['receive_utc'],'receive_mono_s':recv_mono,'first_update_id':U,'final_update_id':u,'previous_update_id':depth['previous_update_id'],'best_bid':best_bid,'best_ask':best_ask,'mid':q['mid'],'spread_bps':q['spread_bps'],'bid_depth_top10_btc':sum(bids[p] for p in sorted(bids,reverse=True)[:10]),'ask_depth_top10_btc':sum(asks[p] for p in sorted(asks)[:10]),'bid_levels_top5_btc':[[p,bids[p]] for p in bid_prices],'ask_levels_top5_btc':[[p,asks[p]] for p in ask_prices],'book_synced':True,'tick_size':TICK_SIZE}
     emit_raw(row)
     if not CAPTURE_ONLY:
      maybe_sweep(recv_mono,recv_wall,d.get('T') or d.get('E'),old_bid,old_ask,best_bid,best_ask);update_pending(recv_mono)
    except Exception:
     with LOCK:COUNTS['bad_rows']+=1
  except Exception as e:
   with LOCK:STATUS['binance']='error:'+type(e).__name__
   time.sleep(1)
  finally:
   try:
    if ws:ws.close()
   except Exception:pass

def binance_trade_worker():
 healer=BinanceTradeHealer()
 while not STOP.is_set():
  ws=None
  try:
   ws=websocket.create_connection(BINANCE_TRADE_WS,timeout=8,enable_multithread=True);ws.settimeout(2)
   with LOCK:STATUS['binance_trades']='connected'
   while not STOP.is_set():
    try:raw=ws.recv()
    except websocket.WebSocketTimeoutException:continue
    recv_wall=time.time();recv_mono=time.monotonic()
    try:
     d=json.loads(raw)
     if d.get('e')!='aggTrade':continue
     healer.process_live_trade(d)
     with LOCK: STATUS['binance_trades']='connected'
    except Exception:
     with LOCK:COUNTS['bad_rows']+=1
  except Exception as e:
   with LOCK:STATUS['binance_trades']='error:'+type(e).__name__
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
      row={'venue':'delta','kind':'trade','symbol':SYMBOL,'sequence':next((d.get(k) for k in ('sequence','seq','sequence_number','update_id','u') if d.get(k) is not None),None),'engine_trade_ts_s':ts_seconds(d.get('t')),'feed_ts_s':ts_seconds(d.get('ts')),'receive_epoch_s':recv_wall,'receive_utc':now_iso(),'receive_mono_s':recv_mono,'price':num(d.get('p')),'quantity_contract_units':num(d.get('s')),'role':d.get('r'),'raw_side_semantics':'preserved_as_exchange_role_field_not_assumed','research_only':True}
      emit_raw(row);continue
     q=quote('delta',bid,ask,engine_ts,recv_wall,recv_mono,typ)
     if q is None:continue
     if typ=='ob_l1':
      with LOCK:COUNTS['delta_ob_l1']+=1
      row={'venue':'delta','kind':'ob_l1','symbol':SYMBOL,'sequence':next((d.get(k) for k in ('sequence','seq','sequence_number','update_id','u') if d.get(k) is not None),None),'engine_ts_s':q['engine_ts_s'],'receive_epoch_s':recv_wall,'receive_utc':q['receive_utc'],'receive_mono_s':recv_mono,'best_bid':bid,'best_ask':ask,'mid':q['mid'],'spread_bps':q['spread_bps'],'bid_size':num(d.get('bs')),'ask_size':num(d.get('as'))}
     else:
      with LOCK:COUNTS['delta_ob_l2']+=1
      row={'venue':'delta','kind':'ob_l2_snapshot','symbol':SYMBOL,'sequence':next((d.get(k) for k in ('sequence','seq','sequence_number','update_id','u') if d.get(k) is not None),None),'engine_ts_s':q['engine_ts_s'],'receive_epoch_s':recv_wall,'receive_utc':q['receive_utc'],'receive_mono_s':recv_mono,'best_bid':bid,'best_ask':ask,'mid':q['mid'],'spread_bps':q['spread_bps'],'bid_levels':(d.get('b') or [])[:20],'ask_levels':(d.get('a') or [])[:20]}
     emit_raw(row)
     if not CAPTURE_ONLY: update_pending(recv_mono)
    except Exception:
     with LOCK:COUNTS['bad_rows']+=1
  except Exception as e:
   with LOCK:STATUS['delta']='error:'+type(e).__name__;time.sleep(1)
  finally:
   try:
    if ws:ws.close()
   except Exception:pass

def main():
 global OUT_RAW,OUT_SWEEPS,OUT_LABELS,RAW_F,RAW_WRITER,SWEEP_F,LABEL_F,CAPTURE_ONLY
 ap=argparse.ArgumentParser(description='Research-only cross-venue capture; no order execution.')
 ap.add_argument('--duration-seconds',type=int,default=600)
 ap.add_argument('--archive-only',action='store_true',help='write raw gzip partitions only; disable all online research evaluation')
 args=ap.parse_args()
 if args.duration_seconds<1: ap.error('--duration-seconds must be >= 1')
 CAPTURE_ONLY=args.archive_only
 # SIGTERM requests a cooperative shutdown so workers stop before gzip trailers are written.
 signal.signal(signal.SIGTERM, lambda *_: STOP.set())
 BASE.mkdir(parents=True,exist_ok=True);stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
 session_id=f'cross_venue_{stamp}'
 OUT_SWEEPS=None if CAPTURE_ONLY else BASE/f'cross_venue_sweeps_{stamp}.jsonl'
 OUT_LABELS=None if CAPTURE_ONLY else BASE/f'cross_venue_labels_{stamp}.jsonl'
 RAW_WRITER=PartitionedGzipJSONLWriter(BASE,session_id=session_id,max_part_bytes=16*1024*1024,compresslevel=4)
 OUT_RAW=RAW_WRITER.current_path
 threads=[]
 try:
  with ExitStack() as stack:
   if not CAPTURE_ONLY:
    SWEEP_F=stack.enter_context(OUT_SWEEPS.open('x',encoding='utf-8',buffering=1))
    LABEL_F=stack.enter_context(OUT_LABELS.open('x',encoding='utf-8',buffering=1))
   else:
    SWEEP_F=LABEL_F=None
   threads=[threading.Thread(target=binance_worker,daemon=True),threading.Thread(target=binance_trade_worker,daemon=True),threading.Thread(target=delta_worker,daemon=True)]
   for t in threads:t.start()
   start=time.monotonic();last_flush=start
   try:
    while time.monotonic()-start<args.duration_seconds and not STOP.is_set():
     now=time.monotonic()
     if not CAPTURE_ONLY: update_pending(now)
     if now-last_flush>=1:
      with LOCK: RAW_WRITER.flush()
      if not CAPTURE_ONLY: SWEEP_F.flush();LABEL_F.flush()
      last_flush=now
     time.sleep(.05)
   except KeyboardInterrupt:pass
   finally:
    if not CAPTURE_ONLY:
     # Drain final candidate labels, then stop workers before closing the gzip writer.
     drain_start=time.monotonic();last_flush=time.monotonic()
     while PENDING and time.monotonic()-drain_start<32.0 and not STOP.is_set():
      now=time.monotonic();update_pending(now)
      if now-last_flush>=1.0:
       with LOCK: RAW_WRITER.flush()
       SWEEP_F.flush();LABEL_F.flush();last_flush=now
      time.sleep(.05)
    STOP.set()
    for t in threads:t.join(timeout=5)
    if not CAPTURE_ONLY:
     SWEEP_F.flush();LABEL_F.flush()
 finally:
  STOP.set()
  for t in threads:
   if t.is_alive(): t.join(timeout=5)
  if RAW_WRITER is not None: RAW_WRITER.close()
 raw_parts=sorted(BASE.glob(f'session_{session_id}_part_*.jsonl.gz'))
 report={'schema':'cross_venue_aligned_capture_report_v1','started_at_utc':stamp,'finished_at_utc':now_iso(),'duration_requested_seconds':args.duration_seconds,'mode':'PUBLIC_RESEARCH_CAPTURE_ONLY','archive_only':CAPTURE_ONLY,'post_capture_label_drain_max_seconds':0 if CAPTURE_ONLY else 32,'binance_symbol':'BTCUSDT USD-M perpetual','delta_symbol':SYMBOL+' Delta India perpetual','raw_path':str(raw_parts[0].relative_to(ROOT)) if raw_parts else None,'raw_partition_paths':[str(p.relative_to(ROOT)) for p in raw_parts],'raw_format':'append-only gzip JSONL partitions; 16 MiB uncompressed target per partition; compression level 4','sweeps_path':str(OUT_SWEEPS.relative_to(ROOT)) if OUT_SWEEPS else None,'labels_path':str(OUT_LABELS.relative_to(ROOT)) if OUT_LABELS else None,'counts':COUNTS,'status':STATUS,'tick_size':TICK_SIZE,'buffers':{'per_venue_quote_history_max':BUFFER_MAX,'trade_flow_window_seconds':FLOW_WINDOW_S,'flow_baseline_max_samples':FLOW_BASELINE_MAX},'sweep_rule':None if CAPTURE_ONLY else {'window_seconds':FLOW_WINDOW_S,'flow_quantile':FLOW_QUANTILE,'minimum_baseline_samples':FLOW_MIN_SAMPLES,'levels':SWEEP_LEVELS,'requires_distinct_aggressive_trade_prices':3,'buffer_seconds':1,'horizons_seconds':[5,15,30]},'timestamp_policy':'Preserve exchange event/transaction timestamps separately from local receive wall/monotonic timestamps; exchange clocks are not assumed synchronized.','real_orders':False,'private_api':False,'credentials_used':False,'execution_enabled':False,'qwen_enabled':False,'notes':['Raw capture is append-only gzip JSONL with exclusive file creation and 16 MiB uncompressed target partitions.','Archive-only mode disables sweep candidate generation and outcome labeling; research evaluation is offline.','Clean shutdown finalizes gzip trailers; sudden SIGKILL or power loss can still leave the active partition incomplete.','Delta trade size is preserved as exchange contract units, not assumed BTC.','Binance aggregate-trade gaps are backfilled from public REST in bounded pages; unresolved gaps are recorded as aggTrade_gap rows and must fail the offline audit.','First observed aggregate-trade ID has no known prior boundary, so completeness before the first observed ID cannot be proven.']}
 report_path=BASE/f'cross_venue_capture_report_{stamp}.json';report_path.write_text(json.dumps(report,indent=2,allow_nan=False));print(json.dumps(report,indent=2),flush=True)
if __name__=='__main__':main()
