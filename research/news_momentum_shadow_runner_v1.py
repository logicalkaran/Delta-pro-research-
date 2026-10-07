"""Continuous NEWS_MOMENTUM_V1 shadow evaluator. No orders/private API."""
from __future__ import annotations
import argparse,json,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; MICRO=ROOT/'data/live_microstructure_state.json'; NEWS=ROOT/'data/processed/news_event_state_v2.json'; OUT=ROOT/'data/processed/news_momentum_shadow_v1.jsonl'; SUMMARY=ROOT/'data/processed/news_momentum_shadow_v1_summary.json'
STOP=5.; TARGET=10.; HOLD=600.; FEE=5.90; TICK=.50

def load(p):
 try:return json.loads(p.read_text())
 except:return {}
def main(seconds=86400):
 end=time.time()+seconds; active=None; stats={'signals':0,'fills':0,'exits':0,'wins':0,'net_bps':0.0}; OUT.parent.mkdir(parents=True,exist_ok=True)
 while time.time()<end:
  now=time.time(); m=load(MICRO); n=load(NEWS); age=now-float(m.get('timestamp',0) or 0); sources={x.get('source') for x in n.get('recent_major_events',[]) if x.get('source')}; w=m.get('windows',{}); p=m.get('price',{}); b=m.get('order_book',{}); mid=float(b.get('mid_price',0)); d5=float(w.get('5',{}).get('delta_pct',0)); d30=float(w.get('30',{}).get('delta_pct',0)); r5=float(p.get('5',{}).get('return_pct',0)); r30=float(p.get('30',{}).get('return_pct',0)); spread=float(b.get('spread',999)); imb=float(b.get('imbalance_5',0))
  direction='LONG' if r5>=.05 and r30>=.05 and d5>=.15 and d30>=.05 and imb>-.35 else 'SHORT' if r5<=-.05 and r30<=-.05 and d5<=-.15 and d30<=-.05 and imb<.35 else 'NONE'
  if age<=2 and len(sources)>=2 and spread<=1 and direction!='NONE' and active is None: active={'opened':now,'direction':direction,'entry':mid+(TICK if direction=='LONG' else -TICK),'event_sources':sorted(sources)}; stats['signals']+=1; stats['fills']+=1
  if active:
   move=(mid-active['entry'])/active['entry']*10000*(1 if active['direction']=='LONG' else -1); reason='TARGET' if move>=TARGET else 'STOP' if move<=-STOP else 'TIME' if now-active['opened']>=HOLD else ''
   if reason:
    net=move-2*FEE; stats['exits']+=1; stats['wins']+=int(net>0); stats['net_bps']+=net; with_open={'ts':now,'event':'NEWS_SHADOW_EXIT','direction':active['direction'],'net_bps':net,'gross_bps':move,'exit_reason':reason,'event_sources':active['event_sources'],'opened':active['opened']}; OUT.open('a').write(json.dumps(with_open,separators=(',',':'))+'\n'); active=None
  SUMMARY.write_text(json.dumps({'strategy':'NEWS_MOMENTUM_V1','status':'SHADOW_ONLY','real_orders':False,**stats},indent=2)); time.sleep(.5)
if __name__=='__main__':
 ap=argparse.ArgumentParser(); ap.add_argument('--seconds',type=int,default=86400); main(ap.parse_args().seconds)
