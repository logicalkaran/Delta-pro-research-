"""Research-only parameter optimizer. Never changes execution settings automatically."""
from pathlib import Path
import json,time,math
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'data/processed/strategy_forward_tournament_v1.jsonl'
OUT=ROOT/'data/processed/scalp_parameter_optimizer_v1.json'
COST_BPS=12.0

def load():
    rows=[]
    if SRC.exists():
        for line in SRC.read_text().splitlines():
            try: rows.append(json.loads(line))
            except: pass
    return rows

def evaluate(rows,min_edge_bps,min_score):
    # Only evaluate already-resolved forward observations; this is a research filter.
    chosen=[]
    for r in rows:
        edge=r.get('expected_edge_bps')
        score=r.get('rank_score')
        if edge is not None and float(edge)>=min_edge_bps and score is not None and float(score)>=min_score:
            chosen.append(r)
    vals=[float(x.get('net_return_pct',0)) for x in chosen]
    if not vals:return {'n':0,'avg':None,'pf':None,'win':None}
    gains=sum(v for v in vals if v>0); losses=abs(sum(v for v in vals if v<0))
    return {'n':len(vals),'avg':sum(vals)/len(vals),'pf':gains/losses if losses else None,'win':sum(v>0 for v in vals)/len(vals)}

def main():
    rows=load(); results=[]
    for edge in (8,10,12,15,18,20,25):
        for score in (70,75,80,82,85,88,90):
            s=evaluate(rows,edge,score)
            stable=bool(s['n']>=30 and s['avg'] is not None and s['avg']>0 and (s['pf'] or 0)>=1.2)
            results.append({'min_expected_edge_bps':edge,'min_rank_score':score,**s,'stable':stable})
    stable=sorted([x for x in results if x['stable']],key=lambda x:(x['avg'],x['pf'] or 0),reverse=True)
    out={'updated_at':time.time(),'source_rows':len(rows),'cost_bps':COST_BPS,'grid':results,'stable_configs':stable[:20],'recommended_config':stable[0] if stable else None,'paper_only':True,'auto_apply':False,'real_orders':False}
    OUT.write_text(json.dumps(out,indent=2)); print(json.dumps({'rows':len(rows),'stable_configs':len(stable),'recommended':out['recommended_config']}))
if __name__=='__main__':main()
