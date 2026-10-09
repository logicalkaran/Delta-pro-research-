"""Multi-timeframe trend/volatility context for 1m/5m paper research; no execution."""
from __future__ import annotations
import argparse,json,math,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'data/processed/live_multi_timeframe_candles_v1.json'
OUT=ROOT/'data/processed/live_multi_timeframe_context_v1.json'

def ema(vals,period):
    if not vals:return None
    a=2/(period+1); e=vals[0]
    for x in vals[1:]:e=a*x+(1-a)*e
    return e

def describe(rows):
    if len(rows)<55:return {'status':'INSUFFICIENT_HISTORY','bars':len(rows),'direction':'UNKNOWN'}
    closes=[float(x['close']) for x in rows]; highs=[float(x['high']) for x in rows]; lows=[float(x['low']) for x in rows]
    e20=ema(closes[-120:],20); e50=ema(closes[-160:],50); c=closes[-1]
    r5=(c/closes[-6]-1)*10000; r20=(c/closes[-21]-1)*10000; r50=(c/closes[-51]-1)*10000
    tr=[]
    for i in range(1,len(rows)):
        tr.append(max(highs[i]-lows[i],abs(highs[i]-closes[i-1]),abs(lows[i]-closes[i-1])))
    atr=sum(tr[-14:])/min(14,len(tr)) if tr else 0
    atr_pct=atr/c*10000 if c else 0
    direction='BULLISH' if c>e20>e50 and r20>0 else 'BEARISH' if c<e20<e50 and r20<0 else 'MIXED'
    regime='HIGH_VOL' if atr_pct>25 else 'LOW_VOL' if atr_pct<6 else 'NORMAL_VOL'
    return {'status':'OK','bars':len(rows),'last_ts':rows[-1]['timestamp'],'close':c,'ema20':e20,'ema50':e50,'return_5_bps':r5,'return_20_bps':r20,'return_50_bps':r50,'atr14_bps':atr_pct,'direction':direction,'volatility_regime':regime}

def build(cache):
    frames=cache.get('candles',{})
    ctx={k:describe(v) for k,v in frames.items()}
    higher=[ctx.get(k,{}) for k in ('15m','1h','4h')]
    dirs=[x.get('direction') for x in higher if x.get('status')=='OK']
    bullish=dirs.count('BULLISH'); bearish=dirs.count('BEARISH')
    alignment='BULLISH' if bullish>=2 and bearish==0 else 'BEARISH' if bearish>=2 and bullish==0 else 'MIXED'
    return {'schema':'live_multi_timeframe_context_v1','updated_at_epoch':time.time(),'symbol':cache.get('symbol','BTCUSD'),'trade_horizons':['1m','5m'],'context_horizons':['15m','1h','4h'],'frames':ctx,'higher_timeframe_alignment':alignment,'policy':'CONTEXT_ONLY_NOT_AN_ENTRY_SIGNAL','research_only':True,'real_orders':False,'live_execution_enabled':False}

def main():
    p=argparse.ArgumentParser(); p.add_argument('--once',action='store_true'); p.add_argument('--interval',type=int,default=30); a=p.parse_args()
    while True:
        try:
            cache=json.loads(SRC.read_text()); result=build(cache); tmp=OUT.with_suffix('.tmp'); tmp.write_text(json.dumps(result,indent=2)); tmp.replace(OUT); print(json.dumps({'status':'OK','alignment':result['higher_timeframe_alignment'],'frames':{k:{'direction':v.get('direction'),'regime':v.get('volatility_regime'),'bars':v.get('bars')} for k,v in result['frames'].items()},'real_orders':False}),flush=True)
        except Exception as e:print(json.dumps({'status':'ERROR','error':type(e).__name__+': '+str(e)[:160],'real_orders':False}),flush=True)
        if a.once:break
        time.sleep(max(10,a.interval))
if __name__=='__main__':main()
