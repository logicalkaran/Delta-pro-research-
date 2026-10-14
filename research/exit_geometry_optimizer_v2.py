"""Paper/research-only MAE/MFE exit geometry optimizer. Never changes execution settings."""
from pathlib import Path
import json,time,math
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'data/processed/scalp_edge_cohorts_v1.jsonl'
OUT=ROOT/'data/processed/exit_geometry_optimizer_v2.json'
COST_BPS=12.0
MIN_SAMPLES=30
STOPS=(5,8,10,12,15,18,20,25,30)
TARGETS=(10,12,15,18,20,25,30,40,50,60)

def f(x,d=0.0):
    try:return float(x)
    except:return d

def load_rows():
    if not SRC.exists(): return []
    out=[]
    for line in SRC.read_text().splitlines():
        try:
            r=json.loads(line)
            if r.get('path_complete') is True and r.get('mae_bps') is not None and r.get('mfe_bps') is not None:
                out.append(r)
        except Exception:
            pass
    return out

def simulate(r,stop,target):
    mae=f(r.get('mae_bps')); mfe=f(r.get('mfe_bps'))
    adverse=-mae
    favorable=mfe
    if adverse>=stop and favorable>=target:
        return None
    if adverse>=stop:
        return -stop-COST_BPS
    if favorable>=target:
        return target-COST_BPS
    return f(r.get('gross_return_pct'))*100-COST_BPS

def stats(vals):
    if not vals:return None
    wins=[v for v in vals if v>0]
    losses=[v for v in vals if v<=0]
    gross_w=sum(wins); gross_l=abs(sum(losses))
    pf=(gross_w/gross_l) if gross_l else math.inf
    return {'samples':len(vals),'avg_net_bps':sum(vals)/len(vals),
            'win_rate':len(wins)/len(vals),'profit_factor':pf,
            'positive':sum(vals)>0}

def main():
    rows=load_rows()
    groups={}
    for r in rows:
        groups.setdefault((r.get('strategy'),int(r.get('horizon') or 0)),[]).append(r)
    reports=[]
    for key,rs in groups.items():
        configs=[]
        for stop in STOPS:
            for target in TARGETS:
                vals=[simulate(r,stop,target) for r in rs]
                vals=[v for v in vals if v is not None]
                s=stats(vals)
                if s and s['samples']>=MIN_SAMPLES:
                    configs.append({'stop_bps':stop,'target_bps':target,'rr':target/stop,**s})
        stable=[x for x in configs if x['avg_net_bps']>0 and x['profit_factor']>=1.2]
        best=max(stable,key=lambda x:(x['avg_net_bps'],x['profit_factor'])) if stable else None
        reports.append({'strategy':key[0],'horizon':key[1],'path_samples':len(rs),'eligible_configs':len(configs),'stable_configs':len(stable),'best':best})
    out={'updated_at':time.time(),'rows':len(rows),'groups':reports,
         'min_samples':MIN_SAMPLES,'cost_bps':COST_BPS,
         'method':'MAE/MFE barrier feasibility only; ambiguous stop-vs-target ordering is excluded.',
         'auto_apply':False,'paper_only':True,'real_orders':False}
    OUT.write_text(json.dumps(out,indent=2))
    print(json.dumps({'rows':len(rows),'groups':len(reports),'stable_total':sum(x['stable_configs'] for x in reports),'best':next((x for x in reports if x['best']),None)}))
if __name__=='__main__': main()
