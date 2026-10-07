#!/usr/bin/env python3
"""Scalper portfolio V2 paper evaluator. Uses V1 signals but applies professional quality/execution filters."""
import json,time,signal,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; STATE=ROOT/'data/live_microstructure_state.json'
OUT=ROOT/'data/processed/scalper_portfolio_paper_v2.jsonl'; SUMMARY=ROOT/'data/processed/scalper_portfolio_paper_v2_summary.json'; KILL=ROOT/'data/run/LIVE_KILL_SWITCH'
sys.path.insert(0,str(ROOT))
from strategy.scalper_portfolio_v1 import evaluate_all
from execution.execution_router_v2 import decide
TICK=.5;CB=.001;MAKER=2.36;TAKER=5.90;STOP=6.0;TARGET=18.0;MAXH=300.;MAXAGE=2.;ENTRYAGE=2.0
PREFERRED={'ABSORPTION_REVERSAL','DELTA_DIVERGENCE','FISHER_MICROSTRUCTURE_PROXY','TREND_REGIME','MOMENTUM_CONTINUATION'}
RUN=True
def stop(a,b):
 global RUN;RUN=False
signal.signal(signal.SIGINT,stop);signal.signal(signal.SIGTERM,stop)
def f(x,d=0):
 try:return float(x)
 except:return d
def tick(x):return round(x/TICK)*TICK
def fee(p,b):return p*CB*b/10000
def bps(a,b):return (b/a-1)*10000 if a else 0
def log(x):
 OUT.parent.mkdir(parents=True,exist_ok=True)
 with OUT.open('a') as h:h.write(json.dumps(x,separators=(',',':'))+'\n')
def main(seconds=86400):
 start=time.time();pos=None;lastts=None;stats={'observations':0,'signals':0,'accepted':0,'rejected':0,'fills':0,'trades':0,'wins':0,'losses':0,'sum_net_bps':0.0,'by_strategy':{},'reject_reasons':{}}
 print('PORTFOLIO V2 | COST-AWARE | 6/18 BPS | 300S | REAL ORDERS OFF',flush=True)
 while RUN and time.time()-start<seconds:
  now=time.time()
  try:s=json.loads(STATE.read_text())
  except:time.sleep(.25);continue
  stats['observations']+=1
  if f(s.get('quality',{}).get('fresh_seconds'),999)>MAXAGE or KILL.exists():time.sleep(.25);continue
  ob=s.get('order_book',{});bid=f(ob.get('best_bid'));ask=f(ob.get('best_ask'));mid=f(ob.get('mid_price'))
  if min(bid,ask,mid)<=0:time.sleep(.25);continue
  last=s.get('last_trade',{});ts=last.get('ts');new=ts is not None and ts!=lastts
  if new:lastts=ts
  if pos:
   side=pos['side'];px=(bid-TICK) if side=='LONG' else (ask+TICK)
   hitstop=px<=pos['stop'] if side=='LONG' else px>=pos['stop']; hittarget=px>=pos['target'] if side=='LONG' else px<=pos['target']
   why='STOP' if hitstop else 'TARGET' if hittarget else 'TIME' if now-pos['open']>=MAXH else None
   if why:
    gross=bps(pos['entry'],px)*(1 if side=='LONG' else -1);net=gross-(MAKER+TAKER)
    row={'ts':now,'event':'V2_EXIT','strategy':pos['strategy'],'side':side,'entry':pos['entry'],'exit':px,'gross_bps':gross,'net_bps':net,'reason':why,'hold_s':now-pos['open']}
    log(row);stats['trades']+=1;stats['sum_net_bps']+=net;stats['wins']+=net>0;stats['losses']+=net<=0
    d=stats['by_strategy'].setdefault(pos['strategy'],{'trades':0,'wins':0,'sum_net_bps':0});d['trades']+=1;d['wins']+=net>0;d['sum_net_bps']+=net
    pos=None
  if not pos:
   sigs=[x for x in evaluate_all(s) if x.action!='NO_TRADE']
   sigs.sort(key=lambda x:(x.strategy not in PREFERRED,x.score),reverse=False)
   if sigs:
    best=sigs[0]
    spread=f(ob.get('spread'));spreadbps=spread/max(mid,1e-9)*10000
    w5=s.get('windows',{}).get('5',{});rd=f(w5.get('delta_pct'));rr=f(s.get('price',{}).get('5',{}).get('return_pct'))*100
    qa=(f(ob.get('bid_depth_5')) if best.action=='LONG' else f(ob.get('ask_depth_5')))*.02
    # Conservative signal-edge haircut; V1 score*3 is deliberately not treated as fully realizable.
    edge=min(30.0,best.expected_move_bps*.65)
    route=decide(signal_edge_bps=edge,spread_bps=spreadbps,queue_ahead=qa,recent_delta=rd,recent_return_bps=rr)
    stats['signals']+=1
    if route.mode=='MAKER': route.mode='REJECT'; route.reason='MAKER_QUEUE_NOT_SIMULATED_V2'
    if route.mode=='REJECT':
     stats['rejected']+=1;stats['reject_reasons'][route.reason]=stats['reject_reasons'].get(route.reason,0)+1
    else:
     stats['accepted']+=1;side=best.action;entry=(ask+TICK if route.mode=='TAKER_PAPER' else bid if side=='LONG' else ask)
     pos={'strategy':best.strategy,'side':side,'route':route.mode,'entry':entry,'open':now,
          'stop':tick(entry*(1-STOP/10000)) if side=='LONG' else tick(entry*(1+STOP/10000)),
          'target':tick(entry*(1+TARGET/10000)) if side=='LONG' else tick(entry*(1-TARGET/10000))}
     stats['fills']+=1;log({'ts':now,'event':'V2_ENTRY','strategy':best.strategy,'action':side,'route':route.mode,'edge_bps':edge,'cost_bps':route.estimated_cost_bps,'position':pos})
  time.sleep(.25)
 summary={**stats,'duration_s':time.time()-start,'open_position':pos,'win_rate':stats['wins']/stats['trades'] if stats['trades'] else 0,'avg_net_bps':stats['sum_net_bps']/stats['trades'] if stats['trades'] else 0,'status':'PAPER_ONLY','real_orders':False,'promotion':'BLOCKED'}
 SUMMARY.write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2),flush=True)
if __name__=='__main__':
 import argparse;p=argparse.ArgumentParser();p.add_argument('--seconds',type=int,default=86400);main(p.parse_args().seconds)
