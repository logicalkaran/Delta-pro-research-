"""Fail-closed production news momentum decision layer. Shadow only."""
from __future__ import annotations
import hashlib,json,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; NEWS=ROOT/'data/processed/news_event_state_v2.json'; MICRO=ROOT/'data/live_microstructure_state.json'; OUT=ROOT/'data/processed/news_momentum_production_state_v2.json'; AUDIT=ROOT/'data/processed/news_momentum_audit_v2.jsonl'
MAX_NEWS=300.; MAX_MICRO=2.; MAX_SPREAD=1.; MIN_SOURCES=2

def load(p):
 try:return json.loads(p.read_text())
 except Exception:return {}

def main():
 now=time.time(); n=load(NEWS); m=load(MICRO); reasons=[]
 sources=[s for s in n.get('recent_major_events',[]) if s.get('source')]
 distinct={s['source'] for s in sources}; news_age=now-float(n.get('timestamp',0) or 0); micro_age=now-float(m.get('timestamp',0) or 0)
 if len(distinct)<MIN_SOURCES: reasons.append('SOURCE_QUORUM_NOT_MET')
 if news_age>MAX_NEWS: reasons.append('NEWS_STATE_STALE')
 if micro_age>MAX_MICRO: reasons.append('MICROSTRUCTURE_STALE')
 w=m.get('windows',{}); p=m.get('price',{}); b=m.get('order_book',{})
 d5=float(w.get('5',{}).get('delta_pct',0)); d30=float(w.get('30',{}).get('delta_pct',0)); r5=float(p.get('5',{}).get('return_pct',0)); r30=float(p.get('30',{}).get('return_pct',0)); imb=float(b.get('imbalance_5',0)); spread=float(b.get('spread',999))
 long=r5>=.05 and r30>=.05 and d5>=.15 and d30>=.05 and imb>-.35; short=r5<=-.05 and r30<=-.05 and d5<=-.15 and d30<=-.05 and imb<.35
 direction='LONG' if long else 'SHORT' if short else 'NONE'
 if direction=='NONE': reasons.append('MOMENTUM_CONFIRMATION_FAILED')
 if spread>MAX_SPREAD: reasons.append('SPREAD_TOO_WIDE')
 event_key=hashlib.sha256(json.dumps(sorted((x.get('source'),x.get('id')) for x in sources)).encode()).hexdigest()[:20]
 decision='SHADOW_SIGNAL' if not reasons else 'BLOCK'
 out={'timestamp':now,'strategy':'NEWS_MOMENTUM_V1','decision':decision,'direction':direction if decision=='SHADOW_SIGNAL' else 'NONE','event_key':event_key,'distinct_sources':sorted(distinct),'news_age_s':news_age,'micro_age_s':micro_age,'features':{'delta5_pct':d5,'delta30_pct':d30,'return5_pct':r5,'return30_pct':r30,'imbalance5':imb,'spread':spread},'reasons':reasons,'execution_mode':'SHADOW_ONLY','real_orders':False,'fail_closed':True}
 OUT.write_text(json.dumps(out,indent=2)); AUDIT.open('a').write(json.dumps(out,separators=(',',':'))+'\n'); print(json.dumps(out,indent=2))
if __name__=='__main__':main()
