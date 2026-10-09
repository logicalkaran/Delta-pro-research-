#!/usr/bin/env python3
"""Read-only synthesis of existing execution-cost research; never changes trading behavior."""
from __future__ import annotations
import argparse, json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DEFAULT_INPUTS={
 'independent_event_fill_study':ROOT/'data/processed/independent_event_fill_study_v1.json',
 'event_move_cost_break_even':ROOT/'data/processed/event_move_cost_break_even_v1.json',
 'opportunity_regime_sensitivity':ROOT/'data/processed/opportunity_regime_sensitivity_v1.json',
}
DEFAULT_OUT=ROOT/'data/processed/execution_economics_synthesis_v1.json'

def _net(row):
    x=row.get('expected_net_per_signal_bps')
    if x is None: x=(row.get('metrics') or {}).get('full_cost',{}).get('expected_net_per_signal_bps')
    try: x=float(x)
    except (TypeError,ValueError): return None
    return x if x==x and abs(x)!=float('inf') else None

def summarize(name, data):
    results=data.get('results',[])
    holdout=[r for r in results if r.get('split')=='holdout' and _net(r) is not None]
    positives=[r for r in holdout if _net(r)>0]
    best=max(holdout,key=_net) if holdout else None
    maker=[r for r in holdout if r.get('route')=='MAKER']
    taker=[r for r in holdout if r.get('route')=='TAKER']
    return {'source':name,'rows_loaded':data.get('rows_loaded',data.get('input_rows')),
      'holdout_result_count':len(holdout),'positive_net_holdout_count':len(positives),
      'best_holdout':None if best is None else {'event':best.get('event'), 'horizon_s':best.get('horizon_s'), 'route':best.get('route'), 'expected_net_bps':_net(best)},
      'maker_holdout_count':len(maker),'maker_positive_count':sum(_net(r)>0 for r in maker),
      'taker_holdout_count':len(taker),'taker_positive_count':sum(_net(r)>0 for r in taker),
      'data_conclusion':data.get('conclusion'),
      'limitations':['Historical results are not a live performance guarantee.', 'Maker fill assumptions do not model queue position or fill-conditioned adverse selection.', 'Existing samples are not independent multi-session replication.']}

def build_report(datasets):
    studies=[summarize(name,data) for name,data in datasets.items()]
    counted=[s for s in studies if s['holdout_result_count']]
    positives=sum(s['positive_net_holdout_count'] for s in counted)
    return {'schema':'execution_economics_synthesis_v1','research_only':True,'real_orders':False,
      'study_count':len(studies),'studies':studies,'aggregate':{
       'studies_with_holdout_results':len(counted),'positive_net_holdout_results_across_studies':positives,
       'interpretation':'No currently reported candidate demonstrates positive expected net return in these evaluated holdout results.' if counted and positives==0 else 'Results are mixed or insufficient; inspect per-study detail.',
       'promotion_decision':'BLOCKED: retain research/paper-only status until independent multi-session results show positive net expectancy after realistic fees, spread, slippage, queue/fill selection, and robustness checks.'},
      'scope':['Reads existing JSON reports only.','Does not tune thresholds, modify production logic, alter risk gates, or place orders.']}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,default=DEFAULT_OUT)
    p.add_argument('--inputs',nargs='*',default=None,help='Optional JSON reports; uses standard research reports by default.')
    a=p.parse_args()
    paths=[Path(x) for x in a.inputs] if a.inputs else list(DEFAULT_INPUTS.values())
    datasets={}
    for path in paths:
        data=json.loads(path.read_text(encoding='utf-8'))
        datasets[path.stem]=data
    report=build_report(datasets)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print(json.dumps({'output':str(a.output),'study_count':report['study_count'],**report['aggregate']},indent=2))
if __name__=='__main__': main()
