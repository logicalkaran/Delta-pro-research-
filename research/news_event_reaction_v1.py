import json,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
NEWS=ROOT/'data/processed/news_event_state_v5.json'; MICRO=ROOT/'data/live_microstructure_state.json'
OUT=ROOT/'data/processed/news_event_reaction_v1.jsonl'; SUMMARY=ROOT/'data/processed/news_event_reaction_v1_summary.json'; STATE=ROOT/'data/processed/news_event_reaction_v1_state.json'
HORIZONS=(5,30,60,300); FEE_BPS=5.90
def load(p):
 try:return json.loads(p.read_text())
 except:return {}
def snap(m):
 b=m.get('order_book',{}); w=m.get('windows',{}); p=m.get('price',{}); return {'ts':time.time(),'mid':float(b.get('mid_price',0) or 0),'spread':float(b.get('spread',999) or 999),'imbalance_5':float(b.get('imbalance_5',0) or 0),'delta_5':float(w.get('5',{}).get('delta_pct',0) or 0),'delta_30':float(w.get('30',{}).get('delta_pct',0) or 0),'return_5':float(p.get('5',{}).get('return_pct',0) or 0),'return_30':float(p.get('30',{}).get('return_pct',0) or 0),'regime':m.get('regime')}
def main(seconds):
 end=time.time()+seconds; active=[]; seen=set(); rows=[]; old=load(STATE); seen.update(old.get('seen_event_ids',[])); rows.extend(old.get('completed',[])); OUT.parent.mkdir(parents=True,exist_ok=True)
 while time.time()<end:
  now=time.time(); n=load(NEWS); m=load(MICRO); age=now-float(m.get('timestamp',0) or 0); s=snap(m)
  if age<=2 and s['mid']>0:
   for ev in n.get('corroborated_events',[]):
    eid=ev.get('cluster_id')
    if eid and eid not in seen and 0 <= now-float(ev.get('event_time_ts',now)) <= 180: active.append({'event_id':eid,'observed_ts':now,'time_delta_sec':ev.get('time_delta_sec'),'similarity':ev.get('similarity'),'sources':ev.get('sources',[]),'titles':ev.get('titles',[]),'baseline':s,'outcomes':{}}); seen.add(eid)
  keep=[]
  for rec in active:
   elapsed=now-rec['observed_ts']
   for h in HORIZONS:
    k=str(h)
    if k not in rec['outcomes'] and elapsed>=h and s['mid']>0:
     gross=(s['mid']/rec['baseline']['mid']-1)*10000; rec['outcomes'][k]={'return_bps':gross,'net_fee_only_bps':gross-2*FEE_BPS,'mid':s['mid'],'spread':s['spread']}
   if len(rec['outcomes'])==len(HORIZONS): rows.append(rec); OUT.open('a').write(json.dumps(rec,separators=(',',':'))+'\n')
   else: keep.append(rec)
  active=keep; stats={'events_seen':len(seen),'completed':len(rows),'active':len(active),'horizons':list(HORIZONS),'roundtrip_fee_bps':2*FEE_BPS}
  for h in HORIZONS:
   vals=[r['outcomes'][str(h)]['return_bps'] for r in rows if str(h) in r.get('outcomes',{})]; net=[v-2*FEE_BPS for v in vals]; stats[str(h)]={'n':len(vals),'mean_return_bps':sum(vals)/len(vals) if vals else 0.0,'mean_net_fee_only_bps':sum(net)/len(net) if net else 0.0,'positive_pct':sum(v>0 for v in vals)/len(vals)*100 if vals else 0.0}
  SUMMARY.write_text(json.dumps(stats,indent=2)); STATE.write_text(json.dumps({'seen_event_ids':sorted(seen),'completed':rows[-100:]},indent=2)); time.sleep(.5)
if __name__=='__main__':
 import argparse; ap=argparse.ArgumentParser(); ap.add_argument('--seconds',type=int,default=86400); main(ap.parse_args().seconds)
