"""Research-only Delta candle cache refresher; public GET endpoints only, no execution."""
from __future__ import annotations
import argparse, json, os, tempfile, time, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BASE='https://api.india.delta.exchange'
RESOLUTIONS={'1m':60,'5m':300,'15m':900,'1h':3600,'4h':14400}
OUT=ROOT/'data/live_candles.json'
MTF=ROOT/'data/processed/live_multi_timeframe_candles_v1.json'

def atomic_json(path:Path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='.'+path.name+'.',dir=str(path.parent),text=True)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:
            json.dump(obj,f,separators=(',',':')); f.flush(); os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        try: os.unlink(tmp)
        except FileNotFoundError: pass

def fetch(resolution:str, lookback_seconds:int, timeout:float=8.0):
    now=int(time.time()); q=urllib.parse.urlencode({'resolution':resolution,'symbol':'BTCUSD','start':now-lookback_seconds,'end':now})
    req=urllib.request.Request(BASE+'/v2/history/candles?'+q,headers={'User-Agent':'btc-research-candle-sync/1.0','Accept':'application/json'})
    with urllib.request.urlopen(req,timeout=timeout) as response: payload=json.loads(response.read().decode())
    if payload.get('success') is False: raise RuntimeError('Delta candle endpoint returned success=false')
    rows=[]
    for raw in payload.get('result',[]):
        try:
            ts=int(raw['time']); o=float(raw['open']); h=float(raw['high']); l=float(raw['low']); c=float(raw['close']); v=float(raw.get('volume',0) or 0)
            if ts<=0 or min(o,h,l,c)<=0 or h<max(o,c,l) or l>min(o,c,h) or v<0: continue
            rows.append({'timestamp':ts,'open':o,'high':h,'low':l,'close':c,'volume':v,'trades':int(raw.get('trades',0) or 0)})
        except (TypeError,ValueError,KeyError): continue
    # Delta returns newest-first. Normalize, deduplicate and retain chronological order.
    by_time={r['timestamp']:r for r in rows}
    return [by_time[t] for t in sorted(by_time)]

def refresh_once():
    now=int(time.time()); frames={}; errors={}
    for res,seconds in RESOLUTIONS.items():
        lookback=12*3600 if res=='1m' else 14*86400
        try:
            rows=fetch(res,lookback)
            if len(rows)<30: raise RuntimeError('too few valid candles: '+str(len(rows)))
            frames[res]=rows[-2400:]
        except Exception as e: errors[res]=type(e).__name__+': '+str(e)[:180]
    if '1m' not in frames: raise RuntimeError('1m refresh failed; existing cache preserved: '+str(errors.get('1m','unknown error')))
    one=frames['1m'][-240:]
    # Keep consumer-compatible live_candles.json as a plain chronological list.
    atomic_json(OUT,one)
    result={'schema':'live_multi_timeframe_candles_v1','symbol':'BTCUSD','updated_at_epoch':time.time(),'source':'Delta public candle REST','research_only':True,'real_orders':False,'frames':{k:{'count':len(v),'first_ts':v[0]['timestamp'],'last_ts':v[-1]['timestamp'],'last_age_seconds':max(0,now-v[-1]['timestamp']-RESOLUTIONS[k])} for k,v in frames.items()},'errors':errors,'candles':frames}
    atomic_json(MTF,result)
    return {'status':'OK' if not errors else 'PARTIAL','one_minute_count':len(one),'frames':result['frames'],'errors':errors,'live_candles_path':str(OUT.relative_to(ROOT)),'mtf_path':str(MTF.relative_to(ROOT)),'real_orders':False}

def main():
    p=argparse.ArgumentParser(); p.add_argument('--once',action='store_true'); p.add_argument('--interval',type=int,default=30); p.add_argument('--seconds',type=int,default=0); a=p.parse_args()
    started=time.time()
    while True:
        try: print(json.dumps({'ts':datetime.now(timezone.utc).isoformat(),**refresh_once()}),flush=True)
        except Exception as e: print(json.dumps({'ts':datetime.now(timezone.utc).isoformat(),'status':'ERROR','error':type(e).__name__+': '+str(e)[:220],'real_orders':False}),flush=True)
        if a.once or (a.seconds and time.time()-started>=a.seconds): break
        time.sleep(max(5,a.interval))
if __name__=='__main__': main()
