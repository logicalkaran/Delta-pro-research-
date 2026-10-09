"""Efficient rolling forward-label worker. Research-only; never executes trades."""
from __future__ import annotations
import bisect,json,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'data/processed/live_microstructure_features_v1.jsonl'
OUT=ROOT/'data/processed/live_microstructure_labeled_v2.jsonl'
MAX_BYTES=20_000_000
HORIZONS=(60,120,180,300)

def read_rows(path):
    rows=[]
    if not path.exists(): return rows
    with path.open(encoding='utf-8',errors='ignore') as f:
        for line in f:
            try:
                r=json.loads(line); ts=float(r['ts']); mid=float(r['mid'])
                if ts>0 and mid>0: rows.append(r)
            except (ValueError,TypeError,KeyError): continue
    rows.sort(key=lambda x:float(x['ts']))
    # De-duplicate repeated timestamps, keeping the latest record.
    dedup={float(r['ts']):r for r in rows}
    return [dedup[t] for t in sorted(dedup)]

def prior_labels(path):
    seen=set()
    if path.exists():
        with path.open(encoding='utf-8',errors='ignore') as f:
            for line in f:
                try: seen.add(float(json.loads(line)['ts']))
                except (ValueError,TypeError,KeyError): pass
    return seen

def label_ready(rows,seen):
    ts=[float(r['ts']) for r in rows]; mids=[float(r['mid']) for r in rows]
    out=[]
    for i,r in enumerate(rows):
        t=ts[i]
        if t in seen: continue
        labels={}; ready=True
        for h in HORIZONS:
            j=bisect.bisect_left(ts,t+h,i+1)
            if j>=len(ts): ready=False; break
            labels[str(h)]={'future_ts':ts[j],'move_bps':(mids[j]/mids[i]-1)*10000}
        if ready:
            x=dict(r); x['labels']=labels; x['label_schema']='forward_mid_return_bps_v2'; x['research_only']=True; x['real_orders']=False
            out.append(x); seen.add(t)
    return out

def append_bounded(path,records):
    if records:
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('a',encoding='utf-8') as f:
            for r in records: f.write(json.dumps(r,separators=(',',':'))+'\n')
    if path.exists() and path.stat().st_size>MAX_BYTES:
        lines=path.read_text(encoding='utf-8',errors='ignore').splitlines()
        keep=lines[-max(1000,len(lines)//2):]
        tmp=path.with_suffix('.tmp'); tmp.write_text('\n'.join(keep)+'\n',encoding='utf-8'); tmp.replace(path)

def run_once():
    rows=read_rows(SRC); seen=prior_labels(OUT); prior_count=len(seen); labeled=label_ready(rows,seen); append_bounded(OUT,labeled)
    return {'source_rows':len(rows),'previously_labeled_timestamps':prior_count,'new_labels':len(labeled),'total_seen_timestamps':len(seen),'last_source_ts':float(rows[-1]['ts']) if rows else None,'output_bytes':OUT.stat().st_size if OUT.exists() else 0,'research_only':True,'real_orders':False}

def main():
    while True:
        try: print(json.dumps({'ts':time.time(),**run_once()}),flush=True)
        except Exception as e: print(json.dumps({'ts':time.time(),'error':type(e).__name__+': '+str(e)[:180],'real_orders':False}),flush=True)
        time.sleep(10)
if __name__=='__main__':main()
