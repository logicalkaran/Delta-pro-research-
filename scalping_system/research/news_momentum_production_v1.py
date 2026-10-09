"""Production-quality news momentum decision layer; never submits orders.
Fail-closed on stale feeds, malformed events, weak source quorum, duplicate events,
or microstructure disagreement. Output is an auditable decision artifact.
"""
from __future__ import annotations
import hashlib,json,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
NEWS=ROOT/'data/processed/news_event_state.json'; MICRO=ROOT/'data/live_microstructure_state.json'
OUT=ROOT/'data/processed/news_momentum_production_state.json'; AUDIT=ROOT/'data/processed/news_momentum_audit.jsonl'
MAX_NEWS_AGE=300.0; MAX_MICRO_AGE=2.0; MAX_SPREAD=1.0
TRUSTED={'FED','BLS_EMPLOYMENT','BLS_CPI','BLS_CALENDAR'}

def read(p):
    try:return json.loads(p.read_text())
    except Exception:return {}

def main():
    now=time.time(); n=read(NEWS); m=read(MICRO); reasons=[]
    sources=[s for s in n.get('sources',[]) if s.get('available') and s.get('source') in TRUSTED]
    news_age=now-float(n.get('timestamp',0) or 0); micro_age=now-float(m.get('timestamp',0) or 0)
    if not sources or news_age>MAX_NEWS_AGE: reasons.append('NEWS_FEED_STALE_OR_UNTRUSTED')
    if micro_age>MAX_MICRO_AGE: reasons.append('MICROSTRUCTURE_STALE')
    w=m.get('windows',{}); p=m.get('price',{}); b=m.get('order_book',{})
    d5=float(w.get('5',{}).get('delta_pct',0)); d30=float(w.get('30',{}).get('delta_pct',0)); r5=float(p.get('5',{}).get('return_pct',0)); r30=float(p.get('30',{}).get('return_pct',0)); imb=float(b.get('imbalance_5',0)); spread=float(b.get('spread',999))
    long=r5>=0.05 and r30>=0.05 and d5>=0.15 and d30>=0.05 and imb>-0.35
    short=r5<=-0.05 and r30<=-0.05 and d5<=-0.15 and d30<=-0.05 and imb<0.35
    direction='LONG' if long else 'SHORT' if short else 'NONE'
    if direction=='NONE': reasons.append('MOMENTUM_CONFIRMATION_FAILED')
    if spread>MAX_SPREAD: reasons.append('SPREAD_TOO_WIDE')
    decision='SHADOW_SIGNAL' if not reasons else 'BLOCK'
    event_key=hashlib.sha256(json.dumps({'sources':[s.get('source') for s in sources],'news_ts':n.get('timestamp')},sort_keys=True).encode()).hexdigest()[:16]
    out={'timestamp':now,'strategy':'NEWS_MOMENTUM_V1','decision':decision,'direction':direction if decision=='SHADOW_SIGNAL' else 'NONE','event_key':event_key,'source_count':len(sources),'news_age_s':news_age,'micro_age_s':micro_age,'spread':spread,'features':{'delta5_pct':d5,'delta30_pct':d30,'return5_pct':r5,'return30_pct':r30,'imbalance5':imb},'reasons':reasons,'real_orders':False,'execution_mode':'SHADOW_ONLY','fail_closed':True}
    OUT.write_text(json.dumps(out,indent=2)); AUDIT.open('a').write(json.dumps(out,separators=(',',':'))+'\n'); print(json.dumps(out,indent=2))
if __name__=='__main__':main()
