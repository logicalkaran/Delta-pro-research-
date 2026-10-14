"""Causal OFI/VAMP/CVD research monitor over the existing public Delta capture.

Research/paper-only. No API credentials, order endpoints, trade placement or policy mutation.
The 3x footprint ratio is recorded as a hypothesis, never a standalone entry trigger.
"""
from __future__ import annotations
import json, math, os, statistics, time
from collections import deque
from datetime import datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
RAW=ROOT/'data/raw/delta_btc_raw.jsonl'
OUT=ROOT/'data/processed/orderflow_pressure_live_v1.json'
LOG=ROOT/'data/processed/orderflow_pressure_events_v1.jsonl'
CURSOR=ROOT/'data/processed/orderflow_pressure_cursor_v1.json'
MAX_LOG_BYTES=10_000_000
WINDOWS=(0.5,1,5,30,60)
MAX_TRADES=5000
MAX_BOOKS=1500
MAX_L1=1500
MAX_EVENT_LATENCY_MS=50.0
MAX_MARKET_AGE_MS=2000.0
MIN_TRADES=10


def num(x,default=0.0):
    try:
        v=float(x)
        return v if math.isfinite(v) else default
    except (TypeError,ValueError): return default

def ts_seconds(message):
    raw=num(message.get('ts') or message.get('t'),0)
    if raw<=0:return 0.0
    # Delta public websocket timestamps observed in this capture are microseconds.
    return raw/1_000_000 if raw>10**14 else raw/1000 if raw>10**11 else raw

def parse_received(value):
    try:return datetime.fromisoformat(str(value).replace('Z','+00:00')).timestamp()
    except (TypeError,ValueError):return None

def percentile(xs,p):
    if not xs:return None
    a=sorted(xs); idx=(len(a)-1)*p/100; lo=int(idx); hi=min(lo+1,len(a)-1)
    return a[lo]+(a[hi]-a[lo])*(idx-lo)

class Monitor:
    def __init__(self):
        self.trades=deque(maxlen=MAX_TRADES); self.books=deque(maxlen=MAX_BOOKS); self.l1=deque(maxlen=MAX_L1)
        self.prev_l1=None; self.ofi_events=deque(maxlen=MAX_L1); self.cvd=0.0
        self.latencies=deque(maxlen=2000); self.history=deque(maxlen=600); self.last_event_ts=0.0; self.last_receive_epoch=0.0
        self.last_message_epoch=0.0; self.parse_errors=0; self.events=0; self.source_resets=0
        self.last_price=0.0; self.last_trade_side='unknown'; self.last_vamp=None
        self.buy_volume_tier=0.0; self.sell_volume_tier=0.0

    def ingest(self,record):
        if not isinstance(record,dict):return
        m=record.get('message',record); typ=m.get('type'); received=parse_received(record.get('received_at'))
        now=time.time(); evt=ts_seconds(m)
        if evt>0:self.last_event_ts=evt
        if received is not None:
            self.last_receive_epoch=received
            if evt>0:
                lag=(received-evt)*1000
                # Negative values can indicate clock skew; never treat them as zero latency.
                self.latencies.append(lag)
        self.last_message_epoch=now; self.events+=1
        if typ=='ob_l1':
            bid=num(m.get('bp')); ask=num(m.get('ap')); bq=max(0,num(m.get('bs'))); aq=max(0,num(m.get('as')))
            if bid<=0 or ask<=0 or ask<bid:return
            cur={'ts':received or now,'event_ts':evt,'recv':received or now,'bid':bid,'ask':ask,'bq':bq,'aq':aq,'mid':(bid+ask)/2,'spread':ask-bid}
            if self.prev_l1:
                p=self.prev_l1
                e=(bq if bid>=p['bid'] else 0)-(p['bq'] if bid<=p['bid'] else 0)-(aq if ask<=p['ask'] else 0)+(p['aq'] if ask>=p['ask'] else 0)
                self.ofi_events.append({'ts':cur['ts'],'ofi':e,'mid':cur['mid']})
            self.prev_l1=cur; self.l1.append(cur)
            den=bq+aq
            self.last_vamp=((bid*aq+ask*bq)/den) if den>0 else None
            return
        if typ=='ob_l2':
            bids=[]; asks=[]
            for x in m.get('b',[]):
                try:
                    p,q=num(x[0]),max(0,num(x[1]))
                    if p>0 and q>0:bids.append((p,q))
                except (TypeError,IndexError):pass
            for x in m.get('a',[]):
                try:
                    p,q=num(x[0]),max(0,num(x[1]))
                    if p>0 and q>0:asks.append((p,q))
                except (TypeError,IndexError):pass
            if bids and asks:
                self.books.append({'ts':received or now,'event_ts':evt,'bid_depth5':sum(q for _,q in bids[:5]),'ask_depth5':sum(q for _,q in asks[:5]),'bid_depth10':sum(q for _,q in bids[:10]),'ask_depth10':sum(q for _,q in asks[:10]),'bid':bids[0][0],'ask':asks[0][0]})
            return
        if typ=='trades':
            px=num(m.get('p')); qty=abs(num(m.get('s')))
            if px<=0 or qty<=0:return
            side='unknown'; q=self.prev_l1
            if q and px>=q['ask']:side='buy'
            elif q and px<=q['bid']:side='sell'
            elif m.get('r')=='m':side='sell'
            elif m.get('r')=='t':side='buy'
            delta=qty if side=='buy' else -qty if side=='sell' else 0.0
            self.trades.append({'ts':received or now,'event_ts':evt,'recv':received or now,'px':px,'qty':qty,'side':side,'delta':delta})
            self.cvd+=delta; self.last_price=px; self.last_trade_side=side

    def snapshot(self,now=None):
        now=time.time() if now is None else float(now)
        latest=self.l1[-1] if self.l1 else None
        mid=latest['mid'] if latest else self.last_price
        age_ms=max(0,(now-latest['recv'])*1000) if latest else None
        trade_age_ms=max(0,(now-self.trades[-1]['recv'])*1000) if self.trades else None
        flow={}; current_delta={}
        for win in WINDOWS:
            rows=[x for x in self.trades if now-win<=x['recv']<=now]
            buys=sum(x['qty'] for x in rows if x['side']=='buy'); sells=sum(x['qty'] for x in rows if x['side']=='sell')
            known=buys+sells; delta=buys-sells
            first=rows[0]['px'] if rows else None; last=rows[-1]['px'] if rows else None
            move=(last/first-1)*10000 if first and last else None
            flow[str(win)]={'trades':len(rows),'buy_volume':buys,'sell_volume':sells,'signed_delta':delta,'delta_ratio':delta/known if known else None,'buy_sell_ratio':buys/sells if sells else None,'price_change_bps':move}
            current_delta[win]=delta
        ofi_rows=[x for x in self.ofi_events if now-5<=x['ts']<=now]
        ofi=sum(x['ofi'] for x in ofi_rows); ofi_mid=ofi/mid if mid else None
        ob_imb=None; vamp=None; vamp_bps=None; spread_bps=None; spread_cross=None
        if latest:
            total=latest['bq']+latest['aq']; ob_imb=(latest['bq']-latest['aq'])/total if total else None
            den=latest['bq']+latest['aq']; vamp=((latest['bid']*latest['aq']+latest['ask']*latest['bq'])/den) if den else None
            vamp_bps=((vamp-latest['mid'])/latest['mid']*10000) if vamp is not None and latest['mid'] else None
            spread_bps=latest['spread']/latest['mid']*10000 if latest['mid'] else None
            vamp_inside=bool(vamp is not None and latest['bid']<=vamp<=latest['ask'])
        book=self.books[-1] if self.books else None
        replenish={'bid':None,'ask':None}
        for side,key in [('bid','bid_depth5'),('ask','ask_depth5')]:
            bs=[x[key] for x in self.books if now-30<=x['ts']<=now]
            if len(bs)>=3:
                trough=min(bs); base=bs[0]; cur=bs[-1]
                replenish[side]=max(0,(cur-trough)/(base-trough)) if base>trough else None
        f500=flow['0.5']; f1=flow['1']; f5=flow['5']; f30=flow['30']; p30=f30['price_change_bps']; d30=f30['delta_ratio']
        short_sign=lambda x: 1 if x is not None and x>0 else -1 if x is not None and x<0 else 0
        incremental_flow={'window_ms':500,'buy_volume':f500['buy_volume'],'sell_volume':f500['sell_volume'],'signed_delta':f500['signed_delta'],'delta_ratio':f500['delta_ratio'],'trade_count':f500['trades'],'directional_persistence_500ms_1s_5s':bool(short_sign(f500['signed_delta'])!=0 and short_sign(f500['signed_delta'])==short_sign(f1['signed_delta'])==short_sign(f5['signed_delta'])),'interpretation':'rolling signed aggressor-volume proxy; not literal unmatched volume, wash-trade detection, or proof of hedge propagation'}
        absorption='NONE'
        if d30 is not None and p30 is not None:
            if d30<=-0.20 and p30>=-0.5 and replenish['bid'] is not None and replenish['bid']>=0.5:absorption='POSSIBLE_BUYER_ABSORPTION'
            elif d30>=0.20 and p30<=0.5 and replenish['ask'] is not None and replenish['ask']>=0.5:absorption='POSSIBLE_SELLER_ABSORPTION'
        vamp_direction='NEUTRAL' if vamp_bps is None or abs(vamp_bps)<0.01 else 'UP' if vamp_bps>0 else 'DOWN'
        ofi_direction='NEUTRAL' if abs(ofi)<1e-9 else 'UP' if ofi>0 else 'DOWN'
        ofi_vamp_disagreement=bool(ofi_direction!='NEUTRAL' and vamp_direction!='NEUTRAL' and ofi_direction!=vamp_direction)
        lat=list(self.latencies)
        lat_nonneg=[x for x in lat if x>=0]
        negative_skew=sum(x<0 for x in lat)
        p50=percentile(lat_nonneg,50); p95=percentile(lat_nonneg,95)
        market_age=max(0,(now-self.last_receive_epoch)*1000) if self.last_receive_epoch else None
        clock_quality=(len(lat)<10 or negative_skew<=max(1,int(len(lat)*0.05)))
        latency_ok=(p95 is not None and p95<=MAX_EVENT_LATENCY_MS and market_age is not None and market_age<=MAX_MARKET_AGE_MS and clock_quality)
        data_ok=latest is not None and age_ms is not None and age_ms<=MAX_MARKET_AGE_MS and flow['5']['trades']>=MIN_TRADES and mid>0
        prior60=[x for x in self.history if now-60<=x['ts']<now and x.get('mid',0)>0]
        prior300=[x for x in self.history if now-300<=x['ts']<now and x.get('mid',0)>0]
        trap_candidate='NONE'
        if len(prior60)>=10 and d30 is not None:
            hi=max(prior60,key=lambda x:x['mid']); lo=min(prior60,key=lambda x:x['mid'])
            if mid>hi['mid'] and hi.get('delta_ratio') is not None and d30<=hi['delta_ratio']-0.20: trap_candidate='POSSIBLE_BULL_TRAP_DELTA_DIVERGENCE'
            elif mid<lo['mid'] and lo.get('delta_ratio') is not None and d30>=lo['delta_ratio']+0.20: trap_candidate='POSSIBLE_BEAR_TRAP_DELTA_DIVERGENCE'
        if trap_candidate=='NONE' and len(prior300)>=20 and d30 is not None:
            hi=max(prior300,key=lambda x:x['mid']); lo=min(prior300,key=lambda x:x['mid'])
            if mid>hi['mid'] and hi.get('delta_ratio') is not None and d30<=hi['delta_ratio']-0.20: trap_candidate='POSSIBLE_BULL_TRAP_DELTA_DIVERGENCE_5M'
            elif mid<lo['mid'] and lo.get('delta_ratio') is not None and d30>=lo['delta_ratio']+0.20: trap_candidate='POSSIBLE_BEAR_TRAP_DELTA_DIVERGENCE_5M'
        ratio=f30['buy_sell_ratio']
        ratio_candidate=(ratio is not None and math.isfinite(ratio) and ratio>=3 and f30['buy_volume']>=100)
        sell_ratio=(f30['sell_volume']/f30['buy_volume']) if f30['buy_volume']>0 else None
        sell_candidate=(sell_ratio is not None and sell_ratio>=3 and f30['sell_volume']>=100)
        if not data_ok: veto='STALE_OR_INSUFFICIENT_DATA'
        elif not latency_ok: veto='EVENT_TO_RECEIVE_LATENCY_UNVERIFIED_OR_OVER_LIMIT'
        else:veto='CALIBRATION_REQUIRED_BEFORE_PAPER_CANDIDATE'
        return {'schema':'orderflow_pressure_live_v1','updated_at_epoch':now,'symbol':'BTCUSD','read_only':True,'research_only':True,'real_orders':False,'live_execution_enabled':False,'source_events_seen':self.events,'source_resets':self.source_resets,'parse_errors':self.parse_errors,'mid_price':mid,'best_bid':latest['bid'] if latest else None,'best_ask':latest['ask'] if latest else None,'spread_bps':spread_bps,'l1_imbalance':ob_imb,'vamp':vamp,'vamp_displacement_bps':vamp_bps,'vamp_direction':vamp_direction,'vamp_inside_spread':vamp_inside,'ofi_direction':ofi_direction,'ofi_vamp_disagreement':ofi_vamp_disagreement,'ofi_5s':ofi,'ofi_5s_normalized_by_mid':ofi_mid,'ofi_event_count_5s':len(ofi_rows),'flow':flow,'incremental_flow_500ms':incremental_flow,'cvd_rolling_observation':self.cvd,'depth_replenishment_30s':replenish,'possible_absorption_candidate':absorption,'delta_divergence_trap_candidate':trap_candidate,'buy_sell_3x_candidate':ratio_candidate,'sell_buy_3x_candidate':sell_candidate,'event_to_receive_ms_estimate':{'samples':len(lat),'negative_clock_skew_samples':negative_skew,'p50_nonnegative_ms':p50,'p95_nonnegative_ms':p95,'max_nonnegative_ms':max(lat_nonneg) if lat_nonneg else None,'clock_skew_can_bias_estimate':True,'not_exchange_order_ack_latency':True},'book_age_ms':age_ms,'trade_age_ms':trade_age_ms,'data_quality_ok':data_ok,'latency_gate_passed':latency_ok,'candidate_veto_reason':veto,'calibration_status':'NOT_CALIBRATED_FOR_THIS_FEATURE_SCHEMA','policy':'OBSERVE_AND_LABEL_ONLY_NO_ENTRY_SIGNAL','ratio_semantics':'30s aggregate aggressor-volume ratio, not per-price footprint imbalance'}

def load_cursor():
    try:return json.loads(CURSOR.read_text())
    except Exception:return {'offset':0,'size':0}
def save_cursor(offset,size):
    CURSOR.parent.mkdir(parents=True,exist_ok=True); tmp=CURSOR.with_suffix('.tmp'); tmp.write_text(json.dumps({'offset':offset,'size':size,'updated_at_epoch':time.time()})); tmp.replace(CURSOR)
def append_log(obj):
    LOG.parent.mkdir(parents=True,exist_ok=True)
    if LOG.exists() and LOG.stat().st_size>MAX_LOG_BYTES:
        lines=LOG.read_text(errors='ignore').splitlines(); LOG.write_text('\n'.join(lines[-max(1000,len(lines)//2):])+'\n')
    with LOG.open('a',encoding='utf-8') as f:f.write(json.dumps(obj,separators=(',',':'),allow_nan=False)+'\n')
def run_once(mon,cursor):
    if not RAW.exists():return cursor
    size=RAW.stat().st_size; offset=int(cursor.get('offset',0))
    if size<offset:
        mon.source_resets+=1; offset=0
    with RAW.open('rb') as f:
        f.seek(offset)
        while True:
            line=f.readline()
            if not line:break
            if not line.endswith(b'\n'):
                f.seek(-len(line),1); break
            offset=f.tell()
            try:mon.ingest(json.loads(line.decode('utf-8')))
            except Exception:mon.parse_errors+=1
    save_cursor(offset,size)
    return {'offset':offset,'size':size}
def main():
    mon=Monitor(); cursor=load_cursor()
    # Replay current bounded capture once so metrics start with context; resume at file end.
    if RAW.exists() and int(cursor.get('offset',0))==0:
        cursor={'offset':0,'size':0}; cursor=run_once(mon,cursor)
    while True:
        try:
            before=mon.events; cursor=run_once(mon,cursor); snap=mon.snapshot()
            snap['events_processed_this_cycle']=mon.events-before
            context_path=ROOT/'data/processed/live_multi_timeframe_context_v1.json'
            try:
                context=json.loads(context_path.read_text())
                snap['higher_timeframe_context']={k:context.get('frames',{}).get(k,{}).get('direction','UNKNOWN') for k in ('15m','1h','4h')}
                snap['higher_timeframe_alignment']=context.get('higher_timeframe_alignment','UNKNOWN')
            except Exception:
                snap['higher_timeframe_context']={'15m':'UNKNOWN','1h':'UNKNOWN','4h':'UNKNOWN'}
                snap['higher_timeframe_alignment']='UNKNOWN'
            if snap.get('mid_price') and snap.get('flow',{}).get('30',{}).get('delta_ratio') is not None:
                mon.history.append({'ts':snap['updated_at_epoch'],'mid':snap['mid_price'],'delta_ratio':snap['flow']['30']['delta_ratio']})
            OUT.parent.mkdir(parents=True,exist_ok=True); tmp=OUT.with_suffix('.tmp'); tmp.write_text(json.dumps(snap,indent=2,allow_nan=False)); tmp.replace(OUT)
            if mon.events>0 and (mon.events-before>0 or int(time.time())%5==0):append_log(snap)
            print(json.dumps({'status':'OK','events':mon.events,'new_events':mon.events-before,'latency_p95_ms':snap['event_to_receive_ms_estimate']['p95_nonnegative_ms'],'veto':snap['candidate_veto_reason'],'absorption':snap['possible_absorption_candidate'],'real_orders':False}),flush=True)
        except Exception as exc:
            print(json.dumps({'status':'ERROR','error':type(exc).__name__+': '+str(exc)[:180],'real_orders':False}),flush=True)
        time.sleep(0.5)
if __name__=='__main__':main()
