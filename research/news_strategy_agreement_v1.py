#!/usr/bin/env python3
import json,time,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
NEWS=ROOT/'data/processed/news_event_state_v5.json'
MICRO=ROOT/'data/live_microstructure_state.json'
OUT=ROOT/'data/processed/news_strategy_agreement_v1.jsonl'
STATE=ROOT/'data/processed/news_strategy_agreement_v1_state.json'
import sys;sys.path.insert(0,str(ROOT))
from strategy.scalper_portfolio_v1 import evaluate_all

def load(p):
    try:return json.loads(p.read_text())
    except:return None

def main(seconds=86400):
    start=time.time(); st=load(STATE) or {'seen':[]}
    seen=set(st.get('seen',[]))
    print('NEWS STRATEGY AGREEMENT V1 | RESEARCH ONLY | REAL ORDERS OFF',flush=True)
    while time.time()-start<seconds:
        ns=load(NEWS); ms=load(MICRO); now=time.time()
        if not ns or not ms:
            time.sleep(1);continue
        for ev in ns.get('corroborated_events',[]):
            eid=ev.get('cluster_id')
            et=float(ev.get('event_time_ts',0))
            if not eid or eid in seen or et<=0 or not (0<=now-et<=180):
                continue
            sigs=evaluate_all(ms)
            active=[{'strategy':x.strategy,'action':x.action,'score':x.score,'expected_move_bps':x.expected_move_bps,'reason':x.reason} for x in sigs if x.action!='NO_TRADE']
            longs=sum(x['action']=='LONG' for x in active); shorts=sum(x['action']=='SHORT' for x in active)
            row={'observed_at':now,'event_id':eid,'event_time_ts':et,'age_s':now-et,
                 'sources':ev.get('sources',[]),'families':ev.get('families',[]),
                 'titles':ev.get('titles',[]),'event_similarity':ev.get('similarity'),
                 'microstructure':{'symbol':ms.get('symbol'),'price':ms.get('order_book',{}).get('mid_price'),
                                   'spread':ms.get('order_book',{}).get('spread'),
                                   'regime':ms.get('regime'),'delta_5':ms.get('windows',{}).get('5',{}).get('delta_pct'),
                                   'return_5':ms.get('price',{}).get('5',{}).get('return_pct')},
                 'active_strategies':active,'long_count':longs,'short_count':shorts,
                 'agreement':'LONG' if longs>=3 and longs>shorts else 'SHORT' if shorts>=3 and shorts>longs else 'MIXED',
                 'status':'RESEARCH_ONLY','real_orders':False}
            OUT.parent.mkdir(parents=True,exist_ok=True)
            with OUT.open('a') as f:f.write(json.dumps(row,separators=(',',':'))+'\n')
            seen.add(eid);st['seen']=sorted(seen);STATE.write_text(json.dumps(st,indent=2))
        time.sleep(1)
if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--seconds',type=int,default=86400)
 main(p.parse_args().seconds)
