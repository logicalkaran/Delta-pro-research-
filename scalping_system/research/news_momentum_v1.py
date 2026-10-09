"""NEWS_MOMENTUM_V1: research/shadow signal detector; never submits orders."""
import json,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
MICRO=ROOT/'data/live_microstructure_state.json'; NEWS=ROOT/'data/processed/news_event_state.json'; OUT=ROOT/'data/processed/news_momentum_signal.json'

def main():
    now=time.time(); m=json.loads(MICRO.read_text()) if MICRO.exists() else {}; n=json.loads(NEWS.read_text()) if NEWS.exists() else {}
    age=now-float(m.get('timestamp',0)); fresh=age<=2.0
    w=m.get('windows',{}); p=m.get('price',{}); book=m.get('order_book',{})
    d5=float(w.get('5',{}).get('delta_pct',0)); d30=float(w.get('30',{}).get('delta_pct',0)); r5=float(p.get('5',{}).get('return_pct',0)); r30=float(p.get('30',{}).get('return_pct',0)); imb=float(book.get('imbalance_5',0)); spread=float(book.get('spread',999))
    sources=[x for x in n.get('sources',[]) if x.get('available')]
    event_ok=bool(sources) and (now-float(n.get('timestamp',0))<=300)
    # Momentum confirmation: direction must agree across price + flow; book cannot strongly contradict.
    long=(r5>=0.05 and r30>=0.05 and d5>=0.15 and d30>=0.05 and imb>-0.35)
    short=(r5<=-0.05 and r30<=-0.05 and d5<=-0.15 and d30<=-0.05 and imb<0.35)
    direction='LONG' if long else 'SHORT' if short else 'NONE'
    signal=bool(fresh and event_ok and direction!='NONE' and spread<=1.0)
    reason=[]
    if not fresh: reason.append('MICRO_STALE')
    if not event_ok: reason.append('NO_FRESH_CONFIRMED_EVENT_SOURCE')
    if direction=='NONE': reason.append('MOMENTUM_NOT_CONFIRMED')
    if spread>1.0: reason.append('SPREAD_TOO_WIDE')
    out={'timestamp':now,'strategy':'NEWS_MOMENTUM_V1','status':'SHADOW_ONLY','signal':signal,'direction':direction if signal else 'NONE','event_sources':len(sources),'micro_age_s':age,'spread':spread,'features':{'delta5_pct':d5,'delta30_pct':d30,'return5_pct':r5,'return30_pct':r30,'imbalance5':imb},'reason':reason,'real_orders':False,'certainty_policy':'No news-only execution; source confirmation plus independent BTC momentum required.'}
    OUT.write_text(json.dumps(out,indent=2)); print(json.dumps(out,indent=2))
if __name__=='__main__': main()
