from pathlib import Path
import json,time
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'data/processed/scalp_edge_cohorts_v1.jsonl'
OUT=ROOT/'data/processed/scalp_edge_evaluation_v1.json'
MIN=30

def main():
    rows=[]
    if SRC.exists():
        for line in SRC.read_text().splitlines():
            try: rows.append(json.loads(line))
            except: pass
    groups={}
    for r in rows: groups.setdefault((r.get('strategy'),int(r.get('horizon',0)),r.get('regime')),[]).append(r)
    reports=[]
    for key,rs in groups.items():
        vals=[float(r.get('net_return_pct',0)) for r in rs]
        n=len(vals); wins=sum(v>0 for v in vals); gains=sum(v for v in vals if v>0); losses=abs(sum(v for v in vals if v<0))
        pf=gains/losses if losses else None
        reports.append({'strategy':key[0],'horizon':key[1],'regime':key[2],'samples':n,'win_rate':wins/n if n else None,'avg_net_pct':sum(vals)/n if n else None,'profit_factor':pf,'eligible':bool(n>=MIN and sum(vals)/n>0 and (pf or 0)>=1.2)})
    eligible=sorted([r for r in reports if r['eligible']],key=lambda r:(r['avg_net_pct'],r['profit_factor'] or 0),reverse=True)
    out={'updated_at':time.time(),'rows':len(rows),'groups':reports,'top_candidates':eligible[:10],'cost_bps':12.0,'paper_only':True,'real_orders':False,'promotion_allowed':False}
    OUT.write_text(json.dumps(out,indent=2)); print(json.dumps({'rows':len(rows),'groups':len(reports),'eligible':len(eligible),'top':eligible[:5]}))
if __name__=='__main__': main()
