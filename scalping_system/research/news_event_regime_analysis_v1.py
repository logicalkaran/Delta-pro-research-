#!/usr/bin/env python3
import json, time, statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SUMMARY=ROOT/'data/processed/news_event_reaction_v1_summary.json'
JOURNAL=ROOT/'data/processed/news_event_reaction_v1.jsonl'
OUT=ROOT/'data/processed/news_event_regime_analysis_v1.json'
THRESH={5:3.0,30:5.0,60:7.0,300:10.0}
def classify(r):
    vals={int(k):float(v.get('return_bps',0.0)) for k,v in r.get('horizons',{}).items()}
    x5,x30,x60,x300=[vals.get(x,0.0) for x in (5,30,60,300)]
    if max(abs(x) for x in (x5,x30,x60,x300)) < 3: return 'NO_REACTION'
    if abs(x5)>=3 and x5*x30<0 and abs(x30)>=5: return 'REVERSAL'
    if abs(x5)>=3 and abs(x30)>=5 and abs(x60)>=7 and x5*x30>0: return 'CONTINUATION'
    if abs(x5)>=3 and abs(x300)>=10 and abs(x5)>abs(x300): return 'ABSORPTION'
    return 'MIXED'
def main():
    rows=[]
    if JOURNAL.exists():
        for line in JOURNAL.read_text().splitlines():
            try: rows.append(json.loads(line))
            except: pass
    groups={}
    for r in rows:
        c=classify(r); groups.setdefault(c,[]).append(r)
    result={'generated_at':time.time(),'status':'RESEARCH_ONLY','events':len(rows),'classification_counts':{k:len(v) for k,v in groups.items()},'regimes':{},'promotion_recommendation':'BLOCKED','real_orders':False}
    for c,rs in groups.items():
        by={h:[] for h in (5,30,60,300)}
        for r in rs:
            for h in by:
                v=r.get('horizons',{}).get(str(h),{}).get('return_bps')
                if v is not None: by[h].append(float(v))
        result['regimes'][c]={str(h):{'n':len(v),'mean_bps':round(statistics.mean(v),3) if v else 0.0,'median_bps':round(statistics.median(v),3) if v else 0.0,'positive_pct':round(100*sum(x>0 for x in v)/len(v),1) if v else 0.0} for h,v in by.items()}
    if result['events']>=30:
        result['promotion_recommendation']='RESEARCH_REVIEW'
    OUT.write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
if __name__=='__main__': main()
