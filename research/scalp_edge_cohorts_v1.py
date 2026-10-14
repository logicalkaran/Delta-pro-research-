from pathlib import Path
import json,time,uuid,sys
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from strategy.predictive_levels_v1 import compute_levels,level_context
STATE=ROOT/'data/live_microstructure_state.json'
CANDLES=ROOT/'data/live_candles.json'
OUT=ROOT/'data/processed/scalp_edge_cohorts_v1.jsonl'
PENDING=ROOT/'data/processed/scalp_edge_pending_v1.json'
COST_BPS=12.0
HORIZONS=(1,2,3,5)

def load(p,d):
    try:return json.loads(p.read_text())
    except:return d

def f(x,d=0.0):
    try:return float(x)
    except:return d

def future_price(cs,target):
    best=None
    for c in cs:
        t=f(c.get('timestamp')); p=f(c.get('close'))
        close_time=t+60.0
        if close_time>=target and (best is None or close_time<best[0]): best=(close_time,p)
    return best[1] if best else None

def future_close_time(cs,target):
    best=None
    for c in cs:
        t=f(c.get('timestamp')); close_time=t+60.0
        if close_time>=target and (best is None or close_time<best): best=close_time
    return best

def path_metrics(cs,entry,start,end,side):
    first_full=((int(start)//60)+1)*60
    path=[c for c in cs if f(c.get('timestamp'))>=first_full and f(c.get('timestamp'))+60<=end]
    if not path or entry<=0:
        return {'path_complete':False,'path_candles':len(path)}
    highs=[f(c.get('high')) for c in path]
    lows=[f(c.get('low')) for c in path]
    if side=='LONG':
        adverse=(min(lows)/entry-1)*10000.0
        favorable=(max(highs)/entry-1)*10000.0
    else:
        adverse=(entry/max(highs)-1)*10000.0
        favorable=(entry/min(lows)-1)*10000.0
    return {'path_complete':True,'path_candles':len(path),'mae_bps':adverse,'mfe_bps':favorable}

def candidates(s,cs):
    if len(cs)<40 or f(s.get('quality',{}).get('fresh_seconds'),999)>2:return []
    ob=s.get('order_book',{}); px=f(ob.get('mid_price'))
    d5=f(s.get('windows',{}).get('5',{}).get('delta_pct'))
    d30=f(s.get('windows',{}).get('30',{}).get('delta_pct'))
    imb=f(ob.get('imbalance_5')); levels=compute_levels(cs,px,ob); out=[]
    for side,level in (('LONG',levels.nearest_support),('SHORT',levels.nearest_resistance)):
        if not level: continue
        ctx=level_context(levels,side,1.25)
        aligned=(side=='LONG' and d5>0 and d30>=d5*0.25) or (side=='SHORT' and d5<0 and d30<=d5*0.25)
        book=(side=='LONG' and imb>0.05) or (side=='SHORT' and imb<-0.05)
        if ctx['eligible'] and (aligned or book):
            for h in HORIZONS:
                out.append({'id':uuid.uuid4().hex,'strategy':'LEVEL_REACTION','direction':side,'entry':px,'issued_at':time.time(),'horizon':h,'level':level,'distance_atr':ctx['distance_atr'],'delta5':d5,'delta30':d30,'imbalance':imb,'regime':levels.regime})
    x=cs[-21:-1]
    if len(x)>=10:
        hi=max(f(c.get('high')) for c in x); lo=min(f(c.get('low')) for c in x)
        low_sweep=px<=lo*1.00025 and d5>0.10 and imb>0.05
        high_sweep=px>=hi*0.99975 and d5<-0.10 and imb<-0.05
        for side,ok,ext in (('LONG',low_sweep,lo),('SHORT',high_sweep,hi)):
            if ok:
                for h in HORIZONS: out.append({'id':uuid.uuid4().hex,'strategy':'LIQUIDITY_SWEEP','direction':side,'entry':px,'issued_at':time.time(),'horizon':h,'sweep_level':ext,'delta5':d5,'delta30':d30,'imbalance':imb,'regime':levels.regime})
    return out

s=load(STATE,{}); cs=load(CANDLES,[]); pending=load(PENDING,[]); now=time.time()
raw_new=candidates(s,cs)
active_keys={(x.get('strategy'),x.get('direction'),x.get('horizon')) for x in pending}
new=[x for x in raw_new if (x.get('strategy'),x.get('direction'),x.get('horizon')) not in active_keys]
pending.extend(new); remaining=[]; resolved=[]
for x in pending:
    if now-f(x['issued_at'])<x['horizon']*60: remaining.append(x); continue
    target=f(x['issued_at'])+x['horizon']*60
    fp=future_price(cs,target); close_time=future_close_time(cs,target)
    if not fp or not close_time: remaining.append(x); continue
    entry=f(x['entry']); gross=((fp/entry)-1)*100 if x['direction']=='LONG' else ((entry/fp)-1)*100
    metrics=path_metrics(cs,entry,f(x['issued_at']),close_time,x['direction'])
    x.update(exit=fp,gross_return_pct=gross,net_return_pct=gross-COST_BPS/100,cost_bps=COST_BPS,resolved_at=now,**metrics); resolved.append(x)
OUT.parent.mkdir(parents=True,exist_ok=True)
with OUT.open('a') as fh:
    for x in resolved: fh.write(json.dumps(x)+'\n')
PENDING.write_text(json.dumps(remaining))
print(json.dumps({'new':len(new),'resolved':len(resolved),'pending':len(remaining),'level_reaction':sum(x['strategy']=='LEVEL_REACTION' for x in new),'liquidity_sweep':sum(x['strategy']=='LIQUIDITY_SWEEP' for x in new),'paper_only':True}))
