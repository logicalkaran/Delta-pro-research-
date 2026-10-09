"""Research-only MAE/MFE and exit-geometry analysis. No execution changes."""
from pathlib import Path
import json,time
ROOT=Path(__file__).resolve().parents[1]
SOURCES=[
    ROOT/'data/processed/strategy_forward_tournament_v1.jsonl',
    ROOT/'data/processed/scalp_edge_cohorts_v1.jsonl'
]
OUT=ROOT/'data/processed/mae_mfe_analysis_v1.json'

def f(x,d=0):
    try:return float(x)
    except:return d

def main():
    rows=[]
    for src in SOURCES:
        if src.exists():
            for line in src.read_text().splitlines():
                try: rows.append(json.loads(line))
                except: pass
    # Only use explicitly captured intratrade path fields; never infer MAE/MFE from closes.
    geom=[]
    for r in rows:
        entry=f(r.get('entry')); exitp=f(r.get('exit'))
        if entry<=0 or exitp<=0: continue
        move=abs(exitp/entry-1)*10000
        geom.append({'strategy':r.get('strategy'),'horizon':r.get('horizon'),'net_bps':f(r.get('net_return_pct'))*100,'move_bps':move})
    by={}
    for x in geom:
        k=(x['strategy'],int(x['horizon'] or 0)); by.setdefault(k,[]).append(x)
    reports=[]
    for k,v in by.items():
        vals=[x['net_bps'] for x in v]
        reports.append({'strategy':k[0],'horizon':k[1],'samples':len(vals),'avg_net_bps':sum(vals)/len(vals),'win_rate':sum(x>0 for x in vals)/len(vals)})
    path_rows=[r for r in rows if r.get('path_complete') is True and r.get('mae_bps') is not None and r.get('mfe_bps') is not None]
    path_groups={}
    for r in path_rows:
        k=(r.get('strategy'),int(r.get('horizon') or 0))
        path_groups.setdefault(k,[]).append(r)
    path_reports=[]
    for k,v in path_groups.items():
        maes=[f(r.get('mae_bps')) for r in v]
        mfes=[f(r.get('mfe_bps')) for r in v]
        path_reports.append({'strategy':k[0],'horizon':k[1],'samples':len(v),'avg_mae_bps':sum(maes)/len(maes),'avg_mfe_bps':sum(mfes)/len(mfes),'max_mae_bps':min(maes),'max_mfe_bps':max(mfes)})
    out={'updated_at':time.time(),'rows':len(rows),'geometry_groups':reports,'path_groups':path_reports,'path_rows':len(path_rows),'mae_available':bool(path_rows),'mfe_available':bool(path_rows),'required_next_fields':['path_complete','mae_bps','mfe_bps','path_candles'],'note':'MAE/MFE uses only fully closed 1m candles after signal issuance and through the first closed candle at or after the requested horizon.','paper_only':True,'auto_apply':False,'real_orders':False}
    OUT.write_text(json.dumps(out,indent=2)); print(json.dumps({'rows':len(rows),'groups':len(reports),'path_rows':len(path_rows),'mae_available':bool(path_rows),'mfe_available':bool(path_rows)}))
if __name__=='__main__': main()
