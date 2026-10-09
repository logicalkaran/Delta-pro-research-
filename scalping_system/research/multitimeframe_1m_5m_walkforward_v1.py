"""Predeclared 1m/5m entry-horizon test with higher-timeframe trend filters. Research only."""
from __future__ import annotations
import json,statistics,time
from pathlib import Path
from bisect import bisect_right
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'data/processed/live_multi_timeframe_candles_v1.json'
OUT=ROOT/'data/processed/multitimeframe_1m_5m_walkforward_v1.json'
COST_BPS=15.8 # conservative assumed round-trip fee + slippage budget; sensitivity still required

def ema(c,period):
 if not c:return None
 a=2/(period+1); value=c[0]
 for x in c[1:]:value=a*x+(1-a)*value
 return value

def trend(rows):
 c=[float(x['close']) for x in rows]
 if len(c)<55:return 'UNKNOWN'
 e20=ema(c[-120:],20); e50=ema(c[-160:],50)
 return 'LONG' if c[-1]>e20>e50 else 'SHORT' if c[-1]<e20<e50 else 'FLAT'
def stats(trades):
 if not trades:return {'n':0,'win_rate':None,'mean_net_bps':None,'profit_factor':None,'positive_net':False}
 wins=[x for x in trades if x>0]; losses=[x for x in trades if x<0]
 gross_win=sum(wins); gross_loss=abs(sum(losses))
 return {'n':len(trades),'win_rate':len(wins)/len(trades),'mean_net_bps':statistics.mean(trades),'median_net_bps':statistics.median(trades),'profit_factor':gross_win/gross_loss if gross_loss else None,'positive_net':statistics.mean(trades)>0}
def frame_returns(rows,entry_tf,context_frames,horizon,required_context):
 interval={'1m':60,'5m':300}[entry_tf]; rows=sorted(rows,key=lambda r:r['timestamp']); ts=[int(r['timestamp']) for r in rows]; close=[float(r['close']) for r in rows]
 context={}
 for tf,ctxrows in context_frames.items():
  xs=sorted(ctxrows,key=lambda r:r['timestamp']); xt=[int(r['timestamp']) for r in xs]
  context[tf]=(xt,xs)
 base=[]; filtered=[]
 for i in range(160,len(rows)-horizon):
  if ts[i]+interval>int(time.time())+interval:continue
  side=trend(rows[:i+1])
  if side=='FLAT' or side=='UNKNOWN':continue
  ret=((close[i+horizon]/close[i])-1)*10000*(1 if side=='LONG' else -1)-COST_BPS
  item={'ts':ts[i],'net_bps':ret,'side':side}
  base.append(item)
  dirs=[]
  for tf,(xt,xs) in context.items():
   if tf not in required_context: continue
   j=bisect_right(xt,ts[i])-1
   # Require the context candle to have fully closed by the entry bar close.
   sec={'15m':900,'1h':3600,'4h':14400}[tf]
   if j>=0 and xt[j]+sec<=ts[i]+interval:
    dirs.append(trend(xs[:j+1]))
   else: dirs.append('UNKNOWN')
  if dirs and all(d==side for d in dirs):filtered.append(item)
 return base,filtered

def main():
 data=json.loads(SRC.read_text()); frames=data['candles']; results={}
 variants={'15m_only':['15m'],'1h_only':['1h'],'15m_1h':['15m','1h'],'15m_1h_4h':['15m','1h','4h']}
 for tf,horizon in [('1m',3),('1m',5),('5m',3),('5m',6)]:
  base,_=frame_returns(frames.get(tf,[]),tf,{k:frames.get(k,[]) for k in ('15m','1h','4h')},horizon,[])
  cut=int(len(base)*.6); base_train=base[:cut]; base_test=base[cut:]
  split_ts=base[cut]['ts'] if cut<len(base) else 0
  variants_result={}
  for name,needed in variants.items():
   _,filt=frame_returns(frames.get(tf,[]),tf,{k:frames.get(k,[]) for k in ('15m','1h','4h')},horizon,needed)
   filt_train=[x for x in filt if x['ts']<split_ts]; filt_test=[x for x in filt if x['ts']>=split_ts]
   variants_result[name]={'context_frames':needed,'train':stats([x['net_bps'] for x in filt_train]),'holdout':stats([x['net_bps'] for x in filt_test]),'promotion_eligible':False}
  results[f'{tf}_h{horizon}']={'horizon_bars':horizon,'cost_assumption_round_trip_bps':COST_BPS,'baseline':{'train':stats([x['net_bps'] for x in base_train]),'holdout':stats([x['net_bps'] for x in base_test])},'context_filters':variants_result}
 report={'schema':'multitimeframe_1m_5m_walkforward_v1','generated_at_epoch':time.time(),'source':'Delta public candles','higher_timeframes':['15m','1h','4h'],'entry_timeframes':['1m','5m'],'results':results,'limitations':['Simple EMA trend rule is a baseline, not a trained strategy','Overlapping horizon outcomes are not independent','Only current cached history was used','Estimated friction is a fixed assumption; actual maker queue/fill and spread must be modeled','No parameter search or strategy promotion performed'],'decision':'RESEARCH_ONLY_NO_PROMOTION','real_orders':False,'live_execution_enabled':False}
 OUT.write_text(json.dumps(report,indent=2)); print(json.dumps(report,indent=2))
if __name__=='__main__':main()
